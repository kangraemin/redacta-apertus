"""Score the anonymiser on the refilled benchmark.

    python -m src.evaluate --bench data/benchmark/benchmark.jsonl --mode full --out outputs/eval_full

Modes: full (rules + Apertus + title veto), apertus (Apertus only), rules (regex only).
Only the *default* decisions count here, i.e. what the clerk sees before touching anything.
"""
import argparse
import json
import re
import time
from collections import defaultdict
from pathlib import Path

from .anonymizer.llm import LLM
from .anonymizer.pipeline import anonymize


def covered(span, red):
    s, t = span
    need = [i for i in range(s, t)]
    hit = sum(1 for i in need if any(a <= i < b for a, b in red))
    return hit / max(1, len(need))


DOB_CUE = re.compile(r"^(?:geboren(?:\s+am)?|geb\.|né(?:e)?\s+le|nat[oa]\s+il|n\.)\s+")


def scored_span(g):
    """Birth dates: the cue word ("geboren am") stays readable, only the date must be covered."""
    if g["type"] == "DATE_OF_BIRTH":
        m = DOB_CUE.match(g["text"])
        if m:
            return g["start"] + m.end(), g["end"]
    return g["start"], g["end"]


def score_doc(row, entities):
    red = [(s, t) for e in entities if e["decision"] == "redact" for s, t in e["mentions"]]
    gold = row["gold"]
    found = [covered(scored_span(g), red) >= 0.9 for g in gold]
    tp_pred = fp_pred = 0
    fps = []
    for s, t in red:
        if any(s < g["end"] and g["start"] < t for g in gold):
            tp_pred += 1
        else:
            fp_pred += 1
            fps.append(row["text"][s:t])
    prot_total = prot_hit = 0
    for name in row.get("protected", []):
        for m in re.finditer(rf"(?<![\wÀ-ÿ]){re.escape(name)}(?![\wÀ-ÿ])", row["text"]):
            if any(m.start() < g["end"] and g["start"] < m.end() for g in gold):
                continue  # same surname as a refilled party: not a protected occurrence
            prot_total += 1
            if any(m.start() < b and a < m.end() for a, b in red):
                prot_hit += 1
    review = sum(1 for e in entities if e["decision"] == "review")
    to_check = sum(1 for e in entities if e["decision"] in ("redact", "review"))
    return {"found": found, "types": [g["type"] for g in gold], "tp_pred": tp_pred, "fp_pred": fp_pred,
            "fps": fps, "missed": [g["text"] for g, f in zip(gold, found) if not f],
            "prot_total": prot_total, "prot_hit": prot_hit, "review": review, "to_check": to_check}


def aggregate(rows, scores):
    agg = defaultdict(lambda: defaultdict(float))
    for r, sc in zip(rows, scores):
        for key in ("all", r["lang"]):
            a = agg[key]
            a["docs"] += 1
            a["gold"] += len(sc["found"])
            a["found"] += sum(sc["found"])
            a["leak_free_docs"] += all(sc["found"])
            a["tp_pred"] += sc["tp_pred"]
            a["fp_pred"] += sc["fp_pred"]
            a["prot_total"] += sc["prot_total"]
            a["prot_hit"] += sc["prot_hit"]
            a["seconds"] += sc.get("seconds", 0)
            a["to_check"] += sc["to_check"]
            for ty, f in zip(sc["types"], sc["found"]):
                a[f"gold_{ty}"] += 1
                a[f"found_{ty}"] += f
    out = {}
    for k, a in agg.items():
        o = {"docs": int(a["docs"]), "gold_mentions": int(a["gold"]),
             "recall": round(a["found"] / max(1, a["gold"]), 4),
             "precision": round(a["tp_pred"] / max(1, a["tp_pred"] + a["fp_pred"]), 4),
             "leak_free_docs": round(a["leak_free_docs"] / max(1, a["docs"]), 4),
             "protected_redacted": round(a["prot_hit"] / max(1, a["prot_total"]), 4),
             "protected_occurrences": int(a["prot_total"]),
             "sec_per_doc": round(a["seconds"] / max(1, a["docs"]), 1),
             "items_to_confirm_per_doc": round(a["to_check"] / max(1, a["docs"]), 1)}
        for ty in ("PERSON", "ORG", "ADDRESS", "DATE_OF_BIRTH", "LOCATION"):
            if a[f"gold_{ty}"]:
                o[f"recall_{ty}"] = round(a[f"found_{ty}"] / a[f"gold_{ty}"], 4)
                o[f"n_{ty}"] = int(a[f"gold_{ty}"])
        out[k] = o
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", default="data/benchmark/benchmark.jsonl")
    ap.add_argument("--mode", default="full", choices=["full", "apertus", "rules"])
    ap.add_argument("--out", default="outputs/eval")
    ap.add_argument("--split", default="test", choices=["dev", "test", "all"])
    ap.add_argument("--limit", type=int, default=0, help="docs per language (0 = all)")
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.bench, encoding="utf-8")]
    rows = [r for r in rows if a.split == "all" or r["split"] == a.split]
    if a.limit:
        per = defaultdict(int)
        keep = []
        for r in rows:
            if per[r["lang"]] < a.limit:
                keep.append(r)
                per[r["lang"]] += 1
        rows = keep
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    pred_path = out / "predictions.jsonl"
    done = {}
    if pred_path.exists():  # resume
        for l in open(pred_path, encoding="utf-8"):
            d = json.loads(l)
            done[d["id"]] = d
    llm = LLM() if a.mode in ("full", "apertus") else None
    with open(pred_path, "a", encoding="utf-8") as f:
        for i, r in enumerate(rows):
            if r["id"] in done:
                continue
            t0 = time.time()
            res = anonymize(r["text"], llm=llm, use_rules=a.mode != "apertus",
                            use_llm=a.mode != "rules", use_veto=a.mode == "full")
            d = {"id": r["id"], "entities": res["entities"], "seconds": round(time.time() - t0, 2)}
            done[r["id"]] = d
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
            f.flush()
            print(f"[{i + 1}/{len(rows)}] {r['id']} {d['seconds']}s", flush=True)
    scores = []
    for r in rows:
        sc = score_doc(r, done[r["id"]]["entities"])
        sc["seconds"] = done[r["id"]]["seconds"]
        sc["id"] = r["id"]
        scores.append(sc)
    metrics = aggregate(rows, scores)
    metrics["_mode"] = a.mode
    metrics["_model"] = llm.model if llm else None
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False))
    with open(out / "errors.jsonl", "w", encoding="utf-8") as f:
        for sc in scores:
            if sc["missed"] or sc["fps"]:
                f.write(json.dumps({"id": sc["id"], "missed": sc["missed"], "false_pos": sc["fps"]},
                                   ensure_ascii=False) + "\n")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
