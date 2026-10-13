"""Evaluation-only baseline: an off-the-shelf multilingual NER model instead of Apertus.

Not part of Redacta. The product image does not install spaCy; this script runs outside Docker:

    python3 -m venv .venv-eval && .venv-eval/bin/pip install -r scripts/requirements-eval.txt
    .venv-eval/bin/python -m spacy download xx_ent_wiki_sm
    .venv-eval/bin/python scripts/baseline_ner.py --variant ner --out outputs/eval_ner
    .venv-eval/bin/python scripts/baseline_ner.py --variant ner_rules --out outputs/eval_ner_rules

Variants:
  ner        every PER and ORG span from spaCy xx_ent_wiki_sm is redacted (entity type only, no role).
  ner_rules  the same spans, plus Redacta's rules: identifier patterns, the bench-list and title veto,
             and the public-body list. Only the Apertus step is replaced, so the gap to Redacta is
             what reading the role adds.
Scoring is src/evaluate.py's, on the same split.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import spacy  # noqa: E402

from src.anonymizer import rules  # noqa: E402
from src.evaluate import aggregate, score_doc  # noqa: E402

LABELS = {"PER": "PERSON", "ORG": "ORG"}


def ner_entities(nlp, text, with_rules):
    comp = rules.composition_span(text) if with_rules else None
    by_name = {}
    for ent in nlp(text).ents:
        if ent.label_ not in LABELS:
            continue
        s, t = ent.start_char, ent.end_char
        name = ent.text
        if with_rules:
            stripped, titled = rules.strip_titles(name)
            if titled or (comp and comp[0] <= s < comp[1]) or rules.after_public_title(text, s):
                continue  # judge, clerk or lawyer: stays
            if rules.is_public_body(name):
                continue  # court, authority, insurer: stays
            s += len(name) - len(stripped)
            name = stripped
            if len(name) < 2:
                continue
        e = by_name.setdefault(name, {"name": name, "kind": LABELS[ent.label_], "decision": "redact",
                                      "source": "ner", "mentions": []})
        e["mentions"].append([s, t])
    out = list(by_name.values())
    if with_rules:
        taken = [(s, t) for e in out for s, t in e["mentions"]]
        for h in rules.find(text):
            if any(h.start < t and s < h.end for s, t in taken):
                continue
            out.append({"name": h.text, "kind": h.kind, "decision": "redact", "source": "rule",
                        "mentions": [[h.start, h.end]]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", default=str(ROOT / "data/benchmark/benchmark.jsonl"))
    ap.add_argument("--variant", default="ner", choices=["ner", "ner_rules"])
    ap.add_argument("--split", default="test", choices=["dev", "test", "all"])
    ap.add_argument("--model", default="xx_ent_wiki_sm")
    ap.add_argument("--out", default="outputs/eval_ner")
    a = ap.parse_args()
    nlp = spacy.load(a.model)
    nlp.max_length = 2_000_000
    rows = [json.loads(l) for l in open(a.bench, encoding="utf-8")]
    rows = [r for r in rows if a.split == "all" or r["split"] == a.split]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    scores = []
    with open(out / "predictions.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            t0 = time.time()
            ents = ner_entities(nlp, r["text"], a.variant == "ner_rules")
            sec = round(time.time() - t0, 2)
            f.write(json.dumps({"id": r["id"], "entities": ents, "seconds": sec}, ensure_ascii=False) + "\n")
            sc = score_doc(r, ents)
            sc["seconds"], sc["id"] = sec, r["id"]
            scores.append(sc)
    metrics = aggregate(rows, scores)
    metrics["_mode"] = a.variant
    metrics["_model"] = f"spacy {spacy.__version__} {a.model} {nlp.meta.get('version')}"
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False))
    with open(out / "errors.jsonl", "w", encoding="utf-8") as f:
        for sc in scores:
            if sc["missed"] or sc["fps"]:
                f.write(json.dumps({"id": sc["id"], "missed": sc["missed"], "false_pos": sc["fps"]},
                                   ensure_ascii=False) + "\n")
    print(json.dumps(metrics["all"], indent=2))


if __name__ == "__main__":
    main()
