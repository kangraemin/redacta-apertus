"""Download already-anonymised Federal Supreme Court decisions from entscheidsuche.ch.

Build-time only. The runtime never touches the network; the files this script
writes are committed under data/raw/.

    python -m src.fetch_decisions --per-lang 60 --out data/raw
"""
import argparse
import html
import json
import re
import time
import urllib.request
from pathlib import Path

SEARCH = "https://entscheidsuche.ch/_search.php"
PLACEHOLDER = re.compile(r"\b[A-Z](?:\.[A-Z])*\.?_{4,}")


def search(lang: str, size: int, offset: int):
    q = {
        "size": size,
        "from": offset,
        "sort": [{"date": "desc"}],
        "query": {"bool": {"must": [
            {"term": {"hierarchy": "CH_BGer"}},
            {"term": {"language": lang}},
            {"range": {"date": {"gte": "2025-06-01"}}},
        ]}},
        "_source": ["id", "date", "language", "attachment.content_url"],
    }
    req = urllib.request.Request(SEARCH, data=json.dumps(q).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return [h["_source"] for h in json.load(r)["hits"]["hits"]]


def html_to_text(raw: str) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", raw, flags=re.S)
    t = re.sub(r"<br\s*/?>|</p>|</div>|</tr>", "\n", t)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    t = t.replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", l).strip() for l in t.split("\n")]
    t = "\n".join(lines)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    # drop the four-language court masthead
    t = re.sub(r"^Bundesgericht\s+Tribunal fédéral\s+Tribunale federale\s+Tribunal federal\s+", "", t)
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-lang", type=int, default=60)
    ap.add_argument("--min-chars", type=int, default=2500)
    ap.add_argument("--max-chars", type=int, default=12000)
    ap.add_argument("--out", default="data/raw")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for lang in ("de", "fr", "it"):
        kept, offset, chambers = 0, 0, {}
        while kept < a.per_lang and offset < 3000:
            hits = search(lang, 100, offset)
            if not hits:
                break
            offset += 100
            for h in hits:
                if kept >= a.per_lang:
                    break
                doc_id = h["id"]
                chamber = doc_id.split("_")[2]
                # spread over chambers: at most a quarter of the sample per chamber
                if chambers.get(chamber, 0) >= max(3, a.per_lang // 4):
                    continue
                path = out / f"{doc_id}.txt"
                if path.exists():
                    kept += 1
                    chambers[chamber] = chambers.get(chamber, 0) + 1
                    continue
                try:
                    with urllib.request.urlopen(h["attachment"]["content_url"], timeout=60) as r:
                        text = html_to_text(r.read().decode("utf-8", "replace"))
                except Exception as e:  # noqa: BLE001
                    print("skip", doc_id, e)
                    continue
                if not (a.min_chars <= len(text) <= a.max_chars):
                    continue
                if len(set(PLACEHOLDER.findall(text))) < 1:
                    continue
                path.write_text(text, encoding="utf-8")
                kept += 1
                chambers[chamber] = chambers.get(chamber, 0) + 1
                time.sleep(0.3)
        print(lang, kept, chambers)


if __name__ == "__main__":
    main()
