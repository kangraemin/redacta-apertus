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
