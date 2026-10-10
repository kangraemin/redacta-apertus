"""Turn already-anonymised decisions back into realistic "raw" decisions with known answers.

Published decisions replace parties with placeholders such as ``A.________`` or
``B.________ AG``. We put synthetic names back in those exact places (and add a
synthetic address or birth date to some parties in the header). Every inserted
string is recorded with its character offsets, so we know exactly what a perfect
anonymiser must remove — no manual annotation needed.

Judges, clerks, lawyers, courts and authorities are never placeholders in the
originals, so they stay real and give us the "must NOT redact" side for free.

    python -m src.build_benchmark --raw data/raw --out data/benchmark --seed 7
"""
import argparse
import json
import random
import re
from pathlib import Path

from .names import COMPANY_WORDS, FIRST, LAST, STREETS, TOWNS

PLACEHOLDER = re.compile(r"\b([A-Z](?:\.[A-Z])*)\.?_{4,}([A-Za-zÀ-ÿ-]*)")
COMPANY_SUFFIX = re.compile(r"^\s+(AG|SA|GmbH|Sàrl|Sagl|S\.A\.|S\.à r\.l\.|SpA|S\.p\.A\.|Ltd|LLC|Inc\.?|"
                            r"Stiftung|Genossenschaft|KLG|Verein|Holding|Treuhand|Immobilien|Fondation|"
                            r"Fondazione|Association|Associazione)\b")
PLACE_CUE = re.compile(r"(?:\bsise?|situé(?:e|s)?|domicilié(?:e|s)?|wohnhaft|residente|domiciliat[oa]|"
                       r"Gemeinde\w*|commune de|comune di|municipalité de|Bezirk|district de|distretto di)\s+(?:à|in|a)?\s*$")
ORG_CUE = re.compile(r"(?:Stiftung|Verein|Firma|Gesellschaft|Fondation|Association|société|Fondazione|"
                     r"Associazione|ditta|società)\s+$", re.I)
STREET_SUFFIX = ("strasse", "weg", "gasse", "platz", "-strasse", "-weg", "-gasse")
# where the header (Rubrum) ends and the body starts
HEADER_END = re.compile(r"^(Gegenstand|Objet|Oggetto)\b", re.M)
DOB_FMT = {
    "de": "geboren am {d}. {m} {y}",
    "fr": "né le {d} {m} {y}",
    "it": "nato il {d} {m} {y}",
}
MONTHS = {
    "de": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
           "September", "Oktober", "November", "Dezember"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
           "septembre", "octobre", "novembre", "décembre"],
    "it": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
           "agosto", "settembre", "ottobre", "novembre", "dicembre"],
}


def lang_of(text: str) -> str:
    head = text[:600]
    if re.search(r"\b(Urteil|Besetzung|Verfahrensbeteiligte)\b", head):
        return "de"
    if re.search(r"\b(Arrêt|Composition|Participants)\b", head):
        return "fr"
    return "it"


def make_entity(rng, lang, key, used_surnames, family):
    """key like 'A' or 'B.A' — placeholders sharing the last letter are relatives."""
    fam = key.split(".")[-1] if "." in key else None
    if fam and fam in family:
        last = family[fam]
    else:
        last = rng.choice([s for s in LAST[lang] if s not in used_surnames])
        used_surnames.add(last)
        if fam:
            family[fam] = last
    return {"first": rng.choice(FIRST[lang]), "last": last}


def refill(text: str, lang: str, rng: random.Random):
    header_m = HEADER_END.search(text)
    header_end = header_m.start() if header_m else min(len(text), 1500)
    used = {w for w in re.findall(r"[A-ZÀ-Ý][a-zà-ÿ]+", text)}
    used_surnames = set(used)
    family, entities, seen_count = {}, {}, {}
    out, gold, pos = [], [], 0
    extras_done = set()

    for m in PLACEHOLDER.finditer(text):
        key, tail = m.group(1), m.group(2)
        after = text[m.end():m.end() + 30]
        if tail and tail.lower().lstrip("-") not in [s.lstrip("-") for s in STREET_SUFFIX]:
            continue  # odd fragment such as "C.________beschränkungen": leave as in original
        out.append(text[pos:m.start()])
        cur = sum(len(s) for s in out)
        ent_id = key
        if tail:  # street name fragment: U.________-strasse
            stem = entities.setdefault(("street", key), rng.choice(STREETS[lang]))
            surface = stem + ("-" if tail.startswith("-") else "") + tail.lstrip("-")
            gold.append({"start": cur, "end": cur + len(surface), "type": "LOCATION", "entity": "loc:" + key})
            out.append(surface)
            pos = m.end()
            continue
        before = text[max(0, m.start() - 30):m.start()]
        if PLACE_CUE.search(before):
            town = entities.setdefault(("town", key), rng.choice(TOWNS[lang])[1])
            gold.append({"start": cur, "end": cur + len(town), "type": "LOCATION", "entity": "loc:" + key})
            out.append(town)
            pos = m.end()
            continue
        if COMPANY_SUFFIX.match(after) or ORG_CUE.search(before):
            ent = entities.setdefault(("org", key), {"name": rng.choice(LAST[lang]) + " " + rng.choice(COMPANY_WORDS[lang])})
            surface, etype = ent["name"], "ORG"
            ent_id = "org:" + key
        else:
            ent = entities.get(("per", key))
            if ent is None:
                ent = make_entity(rng, lang, key, used_surnames, family)
                entities[("per", key)] = ent
            n = seen_count.get(key, 0)
            # first mention full name, later mentions mix full name and surname only
            surface = f"{ent['first']} {ent['last']}" if n == 0 or rng.random() < 0.4 else ent["last"]
            etype = "PERSON"
            ent_id = "per:" + key
            seen_count[key] = n + 1
        gold.append({"start": cur, "end": cur + len(surface), "type": etype, "entity": ent_id})
        out.append(surface)
        pos = m.end()

        # header: give some parties an address or a birth date, like an unredacted draft would have
        if etype == "PERSON" and m.start() < header_end and key not in extras_done and after.startswith(","):
            extras_done.add(key)
            r = rng.random()
            if r < 0.45:
                street, num = rng.choice(STREETS[lang]), rng.randint(1, 120)
                plz, town = rng.choice(TOWNS[lang])
                road = {"de": f"{street}strasse {num}", "fr": f"rue {street} {num}", "it": f"via {street} {num}"}[lang]
                extra = f"{road}, {plz} {town}"
                etype2 = "ADDRESS"
            elif r < 0.75:
                d, mo, y = rng.randint(1, 28), rng.randint(0, 11), rng.randint(1945, 2004)
                extra = DOB_FMT[lang].format(d=d, m=MONTHS[lang][mo], y=y)
                etype2 = "DATE_OF_BIRTH"
            else:
                extra = None
            if extra:
                out.append(", ")
                cur = sum(len(s) for s in out)
                gold.append({"start": cur, "end": cur + len(extra), "type": etype2, "entity": ent_id})
                out.append(extra)
    out.append(text[pos:])
    return "".join(out), gold


def protected_names(text: str):
    """Names that must stay: judges and clerks from the 'Besetzung' block, lawyers from the header."""
    names = set()
    m = re.search(r"(Besetzung|Composition|Composizione)(.*?)(Verfahrensbeteiligte|Participants|Parti|Parties)",
                  text, re.S)
    if m:
        block = m.group(2)
        for w in re.findall(r"\b[A-ZÀ-Ý][a-zà-ÿ]+(?:-[A-ZÀ-Ý][a-zà-ÿ]+)?\b", block):
            if w not in STOP_TITLES:
                names.add(w)
    for m in re.finditer(r"(Rechtsanwält(?:in|e)|Rechtsanwalt|Fürsprecher(?:in)?|Me|Maître|avv\.|avvocat[oa])\s+"
                         r"((?:[A-ZÀ-Ý][a-zà-ÿ]+\s?){1,3})", text):
        for w in m.group(2).split():
            if w not in STOP_TITLES:
                names.add(w)
    return sorted(names)


STOP_TITLES = set("""Bundesrichter Bundesrichterin Bundesrichterinnen Präsident Präsidentin Gerichtsschreiber
Gerichtsschreiberin Juge Juges Juges fédéraux fédérale fédéral Président Présidente Greffier Greffière Mme M MM
Giudice Giudici Presidente Cancelliere Cancelliera Dr Prof Herr Frau Mitglied Mitglieder Le La Les Il I Bundesrichterinnen
Und Et E Präsidierendes Präsidierende Gerichtsschreiberinnen Avocat Avocate Rechtsanwalt Rechtsanwältin
Vizepräsident Vizepräsidentin Vice Juge Federale Federali Bundesgericht Abteilung Me Maître Avv""".split())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--out", default="data/benchmark")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, p in enumerate(sorted(Path(a.raw).glob("*.txt"))):
        text = p.read_text(encoding="utf-8")
        lang = lang_of(text)
        filled, gold = refill(text, lang, rng)
        if not gold:
            continue
        for g in gold:
            g["text"] = filled[g["start"]:g["end"]]
        rows.append({"id": p.stem, "lang": lang, "split": "dev" if i % 5 == 0 else "test", "text": filled, "gold": gold,
                     "protected": protected_names(text), "source_url":
                     f"https://entscheidsuche.ch/docs/CH_BGer/{p.stem}.html"})
    with open(out / "benchmark.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    by = {}
    for r in rows:
        by.setdefault(r["lang"], [0, 0])
        by[r["lang"]][0] += 1
        by[r["lang"]][1] += len(r["gold"])
    print({k: {"docs": v[0], "gold_spans": v[1]} for k, v in by.items()})


if __name__ == "__main__":
    main()
