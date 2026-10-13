"""Write the measured numbers into README.md and technical_report.md (from docs/*.tpl.md).

    python3 scripts/fill_report.py [--results docs/results] [--demo URL]
"""
import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def pct(x):
    return f"{x * 100:.1f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="docs/results")
    ap.add_argument("--demo", default="(link in the submission form)")
    a = ap.parse_args()
    res = ROOT / a.results
    m = {k: json.load(open(res / f"eval_{k}" / "metrics.json")) for k in ("full", "rules", "apertus")}
    before = json.load(open(res / "eval_full_before_fix" / "metrics.json"))["all"]  # first run, no cache
    dev = json.load(open(res / "eval_full_dev" / "metrics.json"))["all"]
    rows = [json.loads(l) for l in open(ROOT / "data/benchmark/benchmark.jsonl", encoding="utf-8")]
    test = [r for r in rows if r["split"] == "test"]
    types = Counter(g["type"] for r in rows for g in r["gold"])
    lang_n = Counter(r["lang"] for r in test)
    f = m["full"]["all"]
    v = {
        "DEMO_URL": a.demo,
        "N_ALL": str(len(rows)), "N_TEST": str(len(test)), "N_DEV": str(len(rows) - len(test)),
        "N_TEST_LANG": ", ".join(f"{lang_n[k]} {k.upper()}" for k in ("de", "fr", "it")),
        "G_ALL": f"{sum(types.values()):,}", "G_TEST": f"{f['gold_mentions']:,}",
        "TYPES": ", ".join(f"{n:,} {t.lower().replace('_', ' ')}" for t, n in types.most_common()),
        "PROT_N": f"{f['protected_occurrences']:,}", "SEC": f"{before['sec_per_doc']:.0f}",
        "R_FULL_V1": pct(before["recall"]), "R_DEV": pct(dev["recall"]), "PROT_DEV": pct(dev["protected_redacted"]),
        "N_DEV_DOCS": str(dev["docs"]),
        "COMMIT": subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                                 text=True).stdout.strip() or "n/a",
    }
    for key, tag in (("full", "FULL"), ("rules", "RULES"), ("apertus", "AP")):
        x = m[key]["all"]
        v[f"R_{tag}"] = pct(x["recall"])
        v[f"P_{tag}"] = pct(x["precision"])
        v[f"LF_{tag}"] = pct(x["leak_free_docs"])
        v[f"PROT_{tag}"] = pct(x["protected_redacted"])
        v[f"IC_{tag}"] = f"{x['items_to_confirm_per_doc']:.1f}"
    ld = lambda d: json.load(open(res / d / "metrics.json"))
    dev1 = ld("eval_full_dev_before_dev_fixes")["all"]
    v2 = ld("eval_full_before_dev_fixes")["all"]
    errs = [json.loads(l) for l in open(res / "eval_full" / "errors.jsonl", encoding="utf-8")]
    v.update({"R_DEV_V1": pct(dev1["recall"]), "PROT_DEV_V1": pct(dev1["protected_redacted"]),
              "P_DEV_V1": pct(dev1["precision"]), "P_DEV": pct(dev["precision"]),
              "R_FULL_V2": pct(v2["recall"]), "P_FULL_V2": pct(v2["precision"]),
              "MISS_N": str(sum(len(e["missed"]) for e in errs)), "FP_N": str(sum(len(e["false_pos"]) for e in errs))})
    for key, tag in (("ner", "NER"), ("ner_rules", "NERR")):
        x = ld(f"eval_{key}")["all"]
        v[f"R_{tag}"], v[f"P_{tag}"] = pct(x["recall"]), pct(x["precision"])
        v[f"LF_{tag}"], v[f"PROT_{tag}"] = pct(x["leak_free_docs"]), pct(x["protected_redacted"])
        v[f"IC_{tag}"] = f"{x['items_to_confirm_per_doc']:.1f}"
    # speed: only runs without cached answers count
    sp = json.load(open(res / "speed" / "speed.json"))
    sec = before["sec_per_doc"]
    v.update({"SEC_FULLRUN": f"{sec:.1f}", "SEC10_METAL": f"{sp['metal_10']['sec_per_doc']:.1f}",
              "SEC10_CPU": f"{sp['docker_cpu_10']['sec_per_doc']:.1f}",
              "CPU_X": f"{sp['docker_cpu_10']['sec_per_doc'] / sp['metal_10']['sec_per_doc']:.1f}", "CPU_VM": sp["docker_cpu_10"]["vm"],
              "CHARS10": f"{sp['chars_first10']:,}", "CHARS_TEST": f"{sp['chars_test']:,}",
              "DAY_METAL": f"{round(86400 / sec, -2):,.0f}",
              "DAY_CPU": f"{round(86400 / sp['docker_cpu_10']['sec_per_doc'], -1):,.0f}",
              "YEAR_H": f"{7883 * sec / 3600:.0f}"})
    lines = ["| | Decisions | Recall | Precision | Leak-free | Protected redacted | Person | Organisation | Address | Date of birth |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for k in ("de", "fr", "it", "all"):
        x = m["full"][k]
        cell = lambda t: f"{pct(x['recall_' + t])} (n={x['n_' + t]})" if ("recall_" + t) in x else "—"
        lines.append(f"| {'All' if k == 'all' else k.upper()} | {x['docs']} | {pct(x['recall'])} | {pct(x['precision'])} | "
                     f"{pct(x['leak_free_docs'])} | {pct(x['protected_redacted'])} | {cell('PERSON')} | {cell('ORG')} | "
                     f"{cell('ADDRESS')} | {cell('DATE_OF_BIRTH')} |")
    v["LANG_TABLE"] = "\n".join(lines)
    notes = res / "error_notes.md"
    v["ERROR_NOTES"] = notes.read_text(encoding="utf-8").strip() if notes.exists() else ""
    for k in list(v):
        v["ERROR_NOTES"] = v["ERROR_NOTES"].replace("{{" + k + "}}", v[k])
    for tpl, out in (("docs/technical_report.tpl.md", "technical_report.md"), ("docs/README.tpl.md", "README.md")):
        s = (ROOT / tpl).read_text(encoding="utf-8")
        for k, val in v.items():
            s = s.replace("{{" + k + "}}", val)
        assert "{{" not in s, [l for l in s.splitlines() if "{{" in l]
        if out == "README.md":  # the template asks to keep the challenge description in the track README
            s += "\n---\n\n## Challenge description (from the Hack Apertus template)\n\n" + \
                 (ROOT / "docs/challenge_track_2b.md").read_text(encoding="utf-8").split("\n", 1)[1].lstrip()
        (ROOT / out).write_text(s, encoding="utf-8")
    print(json.dumps({k: v[k] for k in v if k not in ("LANG_TABLE", "ERROR_NOTES")}, indent=1))


if __name__ == "__main__":
    main()
