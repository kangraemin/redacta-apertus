"""Deterministic detectors. They do two jobs:

1. find identifiers that have a fixed shape (e-mail, phone, IBAN, AHV number,
   licence plate, birth date with a cue word, street address);
2. veto: a name that directly follows a public-role title (judge, clerk, lawyer)
   is never redacted, whatever the model says.
"""
import re
from dataclasses import dataclass


@dataclass
class Hit:
    start: int
    end: int
    kind: str
    text: str


_MONTHS = (r"(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember|"
           r"janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre|"
           r"gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)")
_DATE = rf"(?:\d{{1,2}}\.\s?\d{{1,2}}\.\s?\d{{2,4}}|\d{{1,2}}(?:er|\.)?\s+{_MONTHS}\s+\d{{4}})"
_STREET_WORDS = (r"(?:strasse|str\.|gasse|weg|platz|allee|rain|ring|quai)")
_STREET_PREFIX = (r"(?:rue|avenue|av\.|chemin|ch\.|route|rte|boulevard|bd|place|ruelle|impasse|quai|"
                  r"via|viale|vicolo|piazza|strada|contrada)")

PATTERNS = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("IBAN", re.compile(r"\bCH\d{2}(?:\s?[0-9A-Z]{4}){4}\s?[0-9A-Z]\b")),
    ("AHV", re.compile(r"\b756\.\d{4}\.\d{4}\.\d{2}\b")),
    ("PHONE", re.compile(r"(?:\+41|0041|\b0)\s?\(?\d{2}\)?[\s.]?\d{3}[\s.]?\d{2}[\s.]?\d{2}\b")),
    ("PLATE", re.compile(r"\b(?:AG|AI|AR|BE|BL|BS|FR|GE|GL|GR|JU|LU|NE|NW|OW|SG|SH|SO|SZ|TG|TI|UR|VD|VS|ZG|ZH)"
                         r"\s?\d{1,3}[ ']?\d{3}\b")),
    # the cue word stays readable ("geboren am […]"); only the date itself is the hit (group "v")
    ("DATE_OF_BIRTH", re.compile(rf"\b(?:geboren(?:\s+am)?|geb\.|né(?:e)?\s+le|nat[oa]\s+il|n\.)\s+(?P<v>{_DATE})")),
    ("ADDRESS", re.compile(
        rf"(?:\b[A-ZÄÖÜ][a-zäöüß]+(?:-)?{_STREET_WORDS}\s+\d{{1,4}}[a-z]?"
        rf"|\b{_STREET_PREFIX}\s+(?:[dD]e(?:s|\sla|\sl')?\s|du\s|d'|de\s|dei\s|del(?:la)?\s|ai\s|al\s)?"
        rf"[A-ZÀ-Ý][\wÀ-ÿ'-]*(?:\s[A-ZÀ-Ý][\wÀ-ÿ'-]*){{0,2}}\s+\d{{1,4}}[a-z]?)"
        rf"(?:,\s*(?:CH-)?\d{{4}}\s+(?:St\.\s)?[A-ZÀ-Ý][\wÀ-ÿ-]*(?:\s(?:bei|sur|près)\s[A-ZÀ-Ý][\wÀ-ÿ-]*|\s[A-ZÀ-Ý][\wÀ-ÿ-]*)?)?")),
]

# Titles that announce a public role: the name after them stays in the published decision.
_ROLE_TITLE = (
    r"(?:Bundesrichter(?:in|innen)?|Gerichtsschreiber(?:in)?|Präsident(?:in)?|Vizepräsident(?:in)?|"
    r"Rechtsanw[aä]lt(?:in|e|innen)?|Fürsprecher(?:in)?|Advokat(?:in)?|Staatsanw[aä]lt(?:in)?|"
    r"Juges?\s+fédéra(?:l|le|ux|les)|Greffi(?:er|ère)|Présidente?|Ma[îi]tre|Me|avocate?|"
    r"[Gg]iudic[ei]\s+federal[ei]|Cancellier[ea]|[Pp]residente|avv\.|avvocat[oa]|[Pp]rocureur|[Pp]rocuratore)")
_HONORIFIC = r"(?:\s*(?:,\s*)?(?:Dr\.|Prof\.|lic\.\s?iur\.|MLaw|M\.|Mme|MM\.|Herr|Frau|iur\.|LL\.M\.))*"
# Titles that announce a public role: the name after them stays in the published decision.
PUBLIC_ROLE_CUE = re.compile(_ROLE_TITLE + _HONORIFIC + r"\s*$")
LEADING_TITLE = re.compile(r"^(?:" + _ROLE_TITLE + r"|Dr\.|Prof\.|M\.|Mme|MM\.|Herr|Frau|Signora?|Sig\.)\s+")


def strip_titles(name: str):
    """'Me Christophe Pittet' -> ('Christophe Pittet', True). Second value: a public-role title was removed."""
    public = False
    while True:
        m = LEADING_TITLE.match(name)
        if not m:
            return name, public
        if re.match(_ROLE_TITLE, m.group(0)):
            public = True
        name = name[m.end():]


# Medical titles. A doctor is usually a private person (treating doctor, private expert) whose name the
# court removes, but some are officials (insurer's or court's medical adviser): never kept silently.
MEDICAL_TITLE = re.compile(
    r"^(?:Dr\.?\s*(?:med\.|méd\.)(?:\s*(?:dent|vet)\.)?|med\.(?:\s*(?:dent|vet)\.)?|[Dd]octeur|[Dd]octoresse|"
    r"[Dd]ott(?:ore|oressa|\.(?:ssa)?)|[Dd]r\.?\s+med\b\.?|Arzt|Ärztin|[Mm]édecin|[Mm]edico|[Pp]sychiat\w*)\s+")
_MEDICAL_BEFORE = re.compile(
    r"(?:Dr\.?\s*(?:med\.|méd\.)(?:\s*(?:dent|vet)\.)?|\b[Dd]octeur|\b[Dd]octoresse|\b[Dd]ott(?:ore|oressa|\.(?:ssa)?)"
    r"|\b[Mm]édecin|\b[Mm]edico|\bArzt|\bÄrztin)\s*(?:(?:Dr\.|Prof\.|PD)\s*)*$")


def strip_medical(name: str):
    """'Dr. med. Manuela Steiner' -> ('Manuela Steiner', True). Second value: a medical title was removed."""
    medical = False
    while True:
        m = MEDICAL_TITLE.match(name)
        if not m:
            return name, medical
        medical = True
        name = name[m.end():]


def after_medical_title(text: str, start: int) -> bool:
    window = re.split(r"[;\n]", text[max(0, start - 40):start])[-1]
    return bool(_MEDICAL_BEFORE.search(window.rstrip()))


def find(text: str):
    hits = []
    for kind, rx in PATTERNS:
        for m in rx.finditer(text):
            g = "v" if "v" in rx.groupindex else 0
            hits.append(Hit(m.start(g), m.end(g), kind, m.group(g)))
    hits.sort(key=lambda h: (h.start, -(h.end - h.start)))
    out, last_end = [], -1
    for h in hits:  # drop hits nested in a longer one
        if h.start >= last_end:
            out.append(h)
            last_end = h.end
    return out


def after_public_title(text: str, start: int) -> bool:
    """True if the name starting at `start` directly follows a judge/clerk/lawyer title."""
    window = re.split(r"[;\n]", text[max(0, start - 60):start])[-1]
    return bool(PUBLIC_ROLE_CUE.search(window.rstrip()))


COMPOSITION = re.compile(r"\b(Besetzung|Composition|Composizione)\b(.*?)\b(Verfahrensbeteiligte|Participants|Parti(?:es)?)\b",
                         re.S)


def composition_span(text: str):
    """Character range of the bench list (judges and clerk) in the header, or None."""
    m = COMPOSITION.search(text[:3000])
    return (m.start(2), m.end(2)) if m else None


# Bodies that stay named in Swiss practice even when they are a party: courts, authorities,
# public offices, social-insurance funds, prosecutors and insurance companies.
PUBLIC_BODY = re.compile(
    r"(?i)\b(?:kanton\w*|canton\w*|cantone|cantonale|bund\w*|fédéra\w*|federal\w*|confédération|"
    r"eidgenöss\w*|eidgenoss\w*|gemeinde\w*|commune|comune|municipalit\w*|stadt|ville|città|republi\w*|"
    r"gericht\w*|tribunal\w*|tribunale|cour|corte|justice|juge|giudic\w*|pretur\w*|"
    r"amt|ämter|\w+amt|office|ufficio|service|servizio|sezione|division\w*|direction|direzione|"
    r"departement|département|dipartimento|\w*direktion|\w*departement|verwaltung|administration|amministrazione|"
    r"kammer|\w+kammer|chambre|camera|\w*sekretariat|secrétariat|segretariato|\w*inspektorat|inspection|"
    r"regierungs\w*|conseil d'état|consiglio di stato|staatsanwaltschaft|\w*staatsanwaltschaft|"
    r"ministère public|ministero pubblico|polizei|police|polizia|kommission|commission|commissione|"
    r"\w*behörde|autorité|autorità|kesb|apea|iv-stelle|office ai|ufficio ai|ausgleichskasse|"
    r"\w*kasse|caisse|cassa|suva|versicherung\w*|assurance\w*|assicurazion\w*|mutuel\w*|"
    r"axa|allianz|helvetia|mobiliar|generali|vaudoise|baloise|helsana|swica|sanitas|visana|"
    r"concordia|groupe mutuel|css|sympany|universit\w*|hôpital|ospedale|spital|"
    r"schweizerische eidgenossenschaft|bundesrat|conseil fédéral|consiglio federale|"
    r"staatssekretariat|cna|insai|mpc|ue|eu|union européenne|unione europea|secrétariat d'état|segreteria di stato|sem|estv|afc|fisc|steuer\w*|impôts?|imposte)\b")


def is_public_body(name: str) -> bool:
    return bool(PUBLIC_BODY.search(name))
