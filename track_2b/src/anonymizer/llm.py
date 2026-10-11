"""Minimal OpenAI-compatible client (stdlib only) and the Apertus name-finding prompt."""
import hashlib
import json
import os
import re
import time
import urllib.request

SYSTEM = (
    "You assist a clerk of a Swiss court who prepares a decision for publication. "
    "Swiss practice: the names of parties and of other private persons (relatives, witnesses, victims, "
    "private experts, employers, neighbours) are replaced, and so are private companies and associations "
    "belonging to a party. Judges, court clerks, lawyers, prosecutors, courts, authorities, public "
    "offices, cantons, municipalities, public institutions, social-insurance funds and insurance companies stay, "
    "even when they are a party to the case. "
    "You only list names; you never rewrite the text."
)

USER = """Header of the decision (context only):
<<<
{header}
>>>

Excerpt to analyse:
<<<
{chunk}
>>>

List every name of a person and every name of a company, association or institution that appears in the EXCERPT, copied exactly as written there. For each give its role in this case.
Answer with a JSON array only, no prose. Each item:
{{"name": "<exact text from the excerpt>", "kind": "person" | "organisation", "role": "party" | "private_person" | "private_company" | "judge" | "clerk" | "lawyer" | "prosecutor" | "authority" | "court" | "public_body" | "other"}}
If there is no name, answer []."""

REDACT_ROLES = {"party", "private_person", "private_company", "other"}
# Roles that stay in the published text. The model sometimes invents labels
# ("opponent", "istante", "representative"); anything not clearly public is redacted.
PUBLIC_ROLE_WORDS = ("judge", "juge", "giudic", "richter", "clerk", "greff", "cancell", "schreiber",
                     "lawyer", "attorney", "avocat", "avvocat", "anwalt", "counsel", "representative",
                     "rappresentant", "représentant", "patron", "prosecutor", "procureur", "procurat",
                     "authority", "autorit", "behörde", "court", "tribunal", "gericht", "corte", "cour",
                     "public", "official", "president", "presiden", "präsident", "government", "insur",
                     "administration", "office", "expert_public", "notary", "notaire", "notaio")


def role_redacts(role: str) -> bool:
    # "recourant(e)" (appellant) contains "cour" (court): read it as a party before the substring test
    r = re.sub(r"recour\w*", "party", role.lower())
    if r in REDACT_ROLES:
        return True
    return not any(w in r for w in PUBLIC_ROLE_WORDS)
INNER = re.compile(r"<\|inner_prefix\|>.*?<\|inner_suffix\|>", re.S)


class LLM:
    def __init__(self, base_url=None, model=None, api_key=None, timeout=300):
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL", "")).rstrip("/")
        self.model = model or os.environ.get("LLM_NAME", "swiss-ai/Apertus-v1.5-8B")
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "none")
        self.timeout = timeout
        # Apertus 1.5 deliberates by default; we switch that off for a short, structured answer.
        self.no_think = os.environ.get("LLM_DISABLE_THINKING", "1") == "1"
        self.calls = 0
        self.seconds = 0.0
        # Optional answer cache (temperature 0): the "full" and "apertus" evaluation modes send the
        # same prompts, so the second run reuses the first run's answers.
        self.cache_dir = os.environ.get("LLM_CACHE_DIR")

    def chat(self, system, user, max_tokens=700):
        body = {"model": self.model, "temperature": 0, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if self.no_think:
            body["chat_template_kwargs"] = {"enable_thinking": False}
        cache = None
        if self.cache_dir:
            key = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
            cache = os.path.join(self.cache_dir, key[:2], key + ".json")
            if os.path.exists(cache):
                with open(cache, encoding="utf-8") as f:
                    return json.load(f)["content"]
        req = urllib.request.Request(self.base_url + "/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json",
                                              "Authorization": f"Bearer {self.api_key}"})
        t0 = time.time()
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    data = json.load(r)
                break
            except Exception:  # noqa: BLE001
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
        self.calls += 1
        self.seconds += time.time() - t0
        msg = data["choices"][0]["message"]
        content = INNER.sub("", msg.get("content") or "").strip()
        if cache:
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            with open(cache, "w", encoding="utf-8") as f:
                json.dump({"content": content, "seconds": round(time.time() - t0, 2)}, f, ensure_ascii=False)
        return content

    def find_names(self, header, chunk):
        raw = self.chat(SYSTEM, USER.format(header=header, chunk=chunk))
        return parse_items(raw)


def parse_items(raw: str):
    m = re.search(r"\[.*\]", raw, re.S)
    if not m:
        return []
    txt = m.group(0)
    try:
        items = json.loads(txt)
    except json.JSONDecodeError:
        # salvage objects one by one when the array is cut off or slightly malformed
        items = []
        for o in re.findall(r"\{[^{}]*\}", txt):
            try:
                items.append(json.loads(o))
            except json.JSONDecodeError:
                continue
    out = []
    for it in items:
        if isinstance(it, dict) and isinstance(it.get("name"), str) and it["name"].strip():
            out.append({"name": it["name"].strip(), "kind": str(it.get("kind", "person")).lower(),
                        "role": str(it.get("role", "other")).lower()})
    return out
