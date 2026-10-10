"""Anonymisation pipeline: rules + Apertus propose, the clerk decides.

Output is a list of *entities* (one per person / company / identifier) with every
character span where it occurs. Each entity carries a default decision
("redact", "keep" or "review") and the reason, so the review screen can show why.
"""
import re
import string
import time

from . import rules
from .llm import role_redacts

HEADER_END = re.compile(r"^(Gegenstand|Objet|Oggetto)\b", re.M)
LEGAL_FORM = re.compile(r"\s+(AG|SA|GmbH|Sàrl|Sagl|S\.A\.|SpA|S\.p\.A\.|Ltd|LLC|Inc\.?)$")
LEGAL_WORDS = {"AG", "SA", "GmbH", "Sàrl", "Sagl", "SpA", "Ltd", "LLC", "Inc", "Inc.", "S.A."}
WORD = r"[\wÀ-ÿ]"
ORG_REDACT = {"party", "private_company", "private_person"}
KEEP_ROLES = {"judge", "clerk", "lawyer", "prosecutor", "authority", "court", "public_body"}
# Capitalised words that often stand before a surname but are not first names.
COMMON_CAPS = set("""Herr Frau Monsieur Madame Signor Signora Die Der Das Le La Les Il Lo Gli Mit Von Gegen Contre Contro
Rechtsanwalt Rechtsanwältin Avocat Avocate Avvocato Me Maître Dr Prof Bundesrichter Juge Giudice Präsident Präsidentin
Gerichtsschreiber Gerichtsschreiberin Greffier Greffière Cancelliere Ehemann Ehefrau Sohn Tochter Vater Mutter Bruder Schwester
Beschwerdeführer Beschwerdeführerin Beschwerdegegner Beschwerdegegnerin Recourant Recourante Ricorrente Opposant Intimé Intimée
Und Et Ed Oder Ou O Sowie Ainsi Zeuge Témoin Teste Beistand Curateur Curatrice Arzt Ärztin Médecin""".split())
STOPWORDS = set("""der die das und et le la les il lo gli dei des du von vom zur zum art abs lit ziff al
let cpv cst bgg bge atf dtf sr rs bundesgericht tribunal tribunale""".split())


PARTICLES = ("von ", "de ", "di ", "van ", "da ", "del ", "della ", "du ", "des ")


def looks_like_name(name):
    """Drop what the model lists but is not a name: common nouns, acronyms, role words."""
    if "(" in name or ")" in name:
        return False
    if not name[0].isupper() and not name.lower().startswith(PARTICLES):
        return False  # 'père', 'psychiatre'
    letters = re.sub(r"[^\wÀ-ÿ]", "", name)
    if letters.isupper() and len(letters) <= 5 and not LEGAL_FORM.search(name):
        return False  # 'MPC', 'CNA', 'UE'
    return True


def header_of(text):
    m = HEADER_END.search(text[:4000])
    return text[: m.start()] if m else text[:1200]


def chunks_of(text, size=1800):
    """Paragraph-aligned chunks with their start offsets."""
    out, start, cur = [], 0, ""
    for para in re.split(r"(\n\n)", text):
        if len(cur) + len(para) > size and cur.strip():
            out.append((start, cur))
            start += len(cur)
            cur = ""
        cur += para
    if cur.strip():
        out.append((start, cur))
    return out


def _occurrences(text, surface):
    rx = re.compile(rf"(?<!{WORD}){re.escape(surface)}(?!{WORD})")
    return [(m.start(), m.end()) for m in rx.finditer(text)]


def _labels():
    for c in string.ascii_uppercase:
        yield c
    for c1 in string.ascii_uppercase:
        for c2 in string.ascii_uppercase:
            yield c1 + c2


FIRST_NAME_BEFORE = re.compile(r"([A-ZÀ-Ý][a-zà-ÿ]+(?:-[A-ZÀ-Ý][a-zà-ÿ]+)?) $")


def _with_first_name(text, s, t, taken):
    """'Isabelle Jaquier' when only 'Jaquier' was known: a relative shares the surname."""
    m = FIRST_NAME_BEFORE.search(text[max(0, s - 30):s])
    if not m:
        return [s, t]
    word = m.group(1)
    a = s - len(word) - 1
    if word.lower() in STOPWORDS or rules.LEADING_TITLE.match(word + " ") or rules.is_public_body(word):
        return [s, t]
    if word in COMMON_CAPS or any(a < y and x < s for x, y in taken if (x, y) != (s, t)):
        return [s, t]
    return [a, t]


def anonymize(text, llm=None, use_rules=True, use_llm=True, use_veto=True):
    t0 = time.time()
    header = header_of(text)
    comp = rules.composition_span(text) if use_veto else None

    def vetoed(start):
        if not use_veto:
            return False
        if comp and comp[0] <= start < comp[1]:
            return True
        return rules.after_public_title(text, start)

    # 1) Apertus: names + role, chunk by chunk (the header is passed along as context)
    votes = {}  # surface -> {"kind":..., "roles": [...]}
    raw_items = 0
    if use_llm and llm is not None:
        for off, chunk in chunks_of(text):
            for it in llm.find_names(header[:1500], chunk):
                raw_items += 1
                name, titled = rules.strip_titles(it["name"].strip(" ,;:()«»\"'"))
                name = name.strip(" .,;:")
                if titled:
                    it["role"] = "official (title before the name)"
                if len(name) < 2 or name.lower() in STOPWORDS or "_" in name:
                    continue
                if name not in chunk:
                    continue  # the model must copy text it saw; anything else is dropped
                if not looks_like_name(name):
                    continue
                v = votes.setdefault(name, {"kind": it["kind"], "roles": []})
                v["roles"].append(it["role"])

    entities = []
    for name, v in votes.items():
        roles = v["roles"]
        redact_votes = sum(role_redacts(r) for r in roles)
        keep_votes = len(roles) - redact_votes
        kind = "ORG" if v["kind"].startswith("org") or LEGAL_FORM.search(name) else "PERSON"
        role = max(set(roles), key=roles.count)
        redact = redact_votes >= keep_votes and redact_votes > 0
        reason = f"Apertus: {role}" + (f" ({len(roles)} mentions)" if len(roles) > 1 else "")
        if use_veto and rules.is_public_body(name):
            kind, redact = "ORG", False
            reason += "; rule: court, authority or insurer"
        entities.append({"name": name, "kind": kind, "role": role, "source": "apertus",
                         "decision": "redact" if redact else "keep", "reason": reason})

    # 2) group surname-only mentions with the full name and collect every occurrence in the whole text
    persons = [e for e in entities if e["kind"] == "PERSON"]
    merged = []
    for e in sorted(persons, key=lambda e: -len(e["name"].split())):
        parts = e["name"].split()
        target = None
        for m in merged:
            if parts[-1] == m["name"].split()[-1] and (len(parts) == 1 or len(m["name"].split()) == 1):
                target = m
                break
        if target:
            target["forms"].add(e["name"])
            if e["decision"] == "redact":
                target["decision"] = "redact"
        else:
            e["forms"] = {e["name"]}
            merged.append(e)
    for e in merged:
        toks = e["name"].split()
        if 1 < len(toks) <= 4 and all(t[:1].isupper() for t in toks) and len(toks[-1]) > 2 \
                and toks[-1] not in LEGAL_WORDS and not toks[-1].endswith("."):
            e["forms"].add(e["name"].split()[-1])  # surname alone, e.g. "Bernasconi"
    orgs = []
    for e in entities:
        if e["kind"] == "ORG":
            e["forms"] = {e["name"]}
            base = LEGAL_FORM.sub("", e["name"])
            if base != e["name"] and len(base) > 2:
                e["forms"].add(base)
            orgs.append(e)

    taken = []  # spans already claimed by a longer form

    def claim(s, t):
        for a, b in taken:
            if s < b and a < t:
                return False
        taken.append((s, t))
        return True

    final = []
    for e in sorted(merged + orgs, key=lambda e: -max(len(f) for f in e["forms"])):
        spans = []
        for form in sorted(e["forms"], key=len, reverse=True):
            for s, t in _occurrences(text, form):
                if claim(s, t):
                    spans.append([s, t])
        if not spans:
            continue
        if e["decision"] == "redact" and sum(vetoed(s) for s, _ in spans) * 2 > len(spans):
            e["decision"] = "keep"
            e["reason"] += "; rule: appears with a judge/clerk/lawyer title"
        if e["kind"] == "PERSON" and e["decision"] == "redact":
            spans = [_with_first_name(text, s, t, taken) for s, t in spans]
        e["mentions"] = sorted(spans)
        e["forms"] = sorted(e["forms"])
        final.append(e)

    # 3) rule detectors (fixed-shape identifiers)
    if use_rules:
        redacted = [(s, t) for e in final if e["decision"] == "redact" for s, t in e["mentions"]]
        for h in rules.find(text):
            if any(h.start < t and s < h.end for s, t in taken):
                continue
            linked = any(0 <= h.start - t <= 160 and "\n\n" not in text[t:h.start] for s, t in redacted)
            if h.kind == "ADDRESS" and use_llm and not linked:
                decision, reason = "review", "rule: address, not next to a redacted party"
            else:
                decision, reason = "redact", f"rule: {h.kind.lower().replace('_', ' ')}"
            final.append({"name": h.text, "kind": h.kind, "role": "identifier", "source": "rule",
                          "decision": decision, "reason": reason, "forms": [h.text],
                          "mentions": [[h.start, h.end]]})

    # 4) letters in order of first appearance, as in published decisions (A.________, B.________ ...)
    final.sort(key=lambda e: e["mentions"][0][0])
    gen = _labels()
    for i, e in enumerate(final):
        e["id"] = i
        e["label"] = next(gen) if e["kind"] in ("PERSON", "ORG") and e["decision"] == "redact" else None
    return {"entities": final, "seconds": round(time.time() - t0, 2), "llm_items": raw_items}


PLACEHOLDER_TEXT = {"ADDRESS": "[…]", "DATE_OF_BIRTH": "[…]", "EMAIL": "[…]", "PHONE": "[…]",
                    "IBAN": "[…]", "AHV": "[…]", "PLATE": "[…]", "LOCATION": "[…]"}


def render(text, entities, decisions=None):
    """Apply decisions ({entity id: 'redact'|'keep'}) and return the publishable text."""
    reps = []
    label_gen = _labels()
    labels = {}
    for e in sorted(entities, key=lambda e: e["mentions"][0][0]):
        d = (decisions or {}).get(str(e["id"]), (decisions or {}).get(e["id"], e["decision"]))
        if d != "redact":
            continue
        if e["kind"] in ("PERSON", "ORG"):
            labels[e["id"]] = next(label_gen)
        for s, t in e["mentions"]:
            if e["kind"] in ("PERSON", "ORG"):
                m = LEGAL_FORM.search(text[s:t])
                rep = f"{labels[e['id']]}.________" + (m.group(0) if m else "")
            else:
                rep = PLACEHOLDER_TEXT.get(e["kind"], "[…]")
            reps.append((s, t, rep))
    out, pos = [], 0
    for s, t, rep in sorted(reps):
        if s < pos:
            continue
        out.append(text[pos:s])
        out.append(rep)
        pos = t
    out.append(text[pos:])
    return "".join(out)
