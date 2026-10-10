"""Review server for court clerks. Standard library only, so the container needs nothing but Python.

    python -m src.app            # serves http://localhost:8000

On start it analyses the decisions in data/sample/ in the background. A clerk can
also paste a new decision. Every approval is written to outputs/audit.jsonl.
"""
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .anonymizer.llm import LLM
from .anonymizer.pipeline import anonymize, render

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "data" / "sample"
OUT = Path(os.environ.get("OUTPUT_DIR", ROOT / "outputs"))
STATIC = ROOT / "src" / "static"
DOCS = {}  # id -> {"id", "title", "lang", "text", "status", "result", "error"}
LOCK = threading.Lock()
QUEUE = []
QUEUE_EVT = threading.Event()


def lang_of(text):
    head = text[:800]
    if re.search(r"\b(Urteil|Besetzung|Verfahrensbeteiligte|Verfügung)\b", head):
        return "de"
    if re.search(r"\b(Arrêt|Composition|Participants)\b", head):
        return "fr"
    return "it"


def title_of(text):
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:80]
    return "untitled"


def add_doc(doc_id, text, title=None):
    with LOCK:
        DOCS[doc_id] = {"id": doc_id, "title": title or title_of(text), "lang": lang_of(text), "text": text,
                        "status": "queued", "result": None, "error": None, "decisions": {}}
        cached = OUT / "review" / f"{doc_id}.json"
        if cached.exists():
            saved = json.loads(cached.read_text(encoding="utf-8"))
            if saved.get("text") == text:
                DOCS[doc_id].update(status="ready", result=saved["result"], decisions=saved.get("decisions", {}))
                return
        QUEUE.append(doc_id)
    QUEUE_EVT.set()


def worker():
    llm = LLM()
    while True:
        QUEUE_EVT.wait()
        with LOCK:
            doc_id = QUEUE.pop(0) if QUEUE else None
            if not QUEUE:
                QUEUE_EVT.clear()
        if doc_id is None:
            continue
        doc = DOCS[doc_id]
        doc["status"] = "analysing"
        t0 = time.time()
        try:
            res = anonymize(doc["text"], llm=llm)
            doc["result"] = res
            doc["status"] = "ready"
            save(doc)
            print(f"[anonymiser] {doc_id}: {len(res['entities'])} items in {time.time() - t0:.1f}s", flush=True)
        except Exception as e:  # noqa: BLE001
            doc["status"] = "error"
            doc["error"] = f"{type(e).__name__}: {e}"
            print(f"[anonymiser] {doc_id} failed: {doc['error']}", flush=True)


def save(doc):
    (OUT / "review").mkdir(parents=True, exist_ok=True)
    (OUT / "review" / f"{doc['id']}.json").write_text(json.dumps(
        {"text": doc["text"], "result": doc["result"], "decisions": doc["decisions"]}, ensure_ascii=False),
        encoding="utf-8")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", headers=None):
        data = body if isinstance(body, bytes) else (
            json.dumps(body, ensure_ascii=False).encode() if not isinstance(body, str) else body.encode())
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/index.html"):
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if p == "/api/docs":
            return self._send(200, [{k: d[k] for k in ("id", "title", "lang", "status")} |
                                    {"approved": bool(d.get("approved"))} for d in DOCS.values()])
        if p == "/api/config":
            llm = LLM()
            return self._send(200, {"model": llm.model, "endpoint": llm.base_url})
        m = re.match(r"^/api/doc/([\w.-]+)$", p)
        if m and m.group(1) in DOCS:
            d = DOCS[m.group(1)]
            return self._send(200, {k: d[k] for k in ("id", "title", "lang", "text", "status", "result",
                                                     "error", "decisions")})
        m = re.match(r"^/api/export/([\w.-]+)$", p)
        if m and m.group(1) in DOCS:
            d = DOCS[m.group(1)]
            if not d["result"]:
                return self._send(409, {"error": "not analysed yet"})
            txt = render(d["text"], d["result"]["entities"], d["decisions"])
            return self._send(200, txt, "text/plain; charset=utf-8",
                              {"Content-Disposition": f'attachment; filename="{d["id"]}_anonymised.txt"'})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        p = self.path
        if p == "/api/analyse":
            b = self._body()
            text = (b.get("text") or "").strip()
            if len(text) < 50:
                return self._send(400, {"error": "paste the full decision text"})
            doc_id = "pasted-" + uuid.uuid4().hex[:8]
            add_doc(doc_id, text, b.get("title"))
            return self._send(200, {"id": doc_id})
        m = re.match(r"^/api/preview/([\w.-]+)$", p)
        if m and m.group(1) in DOCS:
            d = DOCS[m.group(1)]
            dec = self._body().get("decisions", {})
            return self._send(200, {"text": render(d["text"], d["result"]["entities"], dec)})
        m = re.match(r"^/api/approve/([\w.-]+)$", p)
        if m and m.group(1) in DOCS:
            d = DOCS[m.group(1)]
            b = self._body()
            d["decisions"] = b.get("decisions", {})
            d["approved"] = True
            save(d)
            ents = {str(e["id"]): e for e in d["result"]["entities"]}
            changed = [{"entity": ents[k]["name"], "kind": ents[k]["kind"], "proposed": ents[k]["decision"],
                        "final": v} for k, v in d["decisions"].items() if k in ents and ents[k]["decision"] != v]
            entry = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "doc": d["id"],
                     "reviewer": b.get("reviewer") or "clerk", "model": LLM().model,
                     "redacted": sum(1 for k, e in ents.items() if d["decisions"].get(k, e["decision"]) == "redact"),
                     "changed_by_reviewer": changed}
            OUT.mkdir(parents=True, exist_ok=True)
            with open(OUT / "audit.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            return self._send(200, {"ok": True, "audit": entry})
        return self._send(404, {"error": "not found"})


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=worker, daemon=True).start()
    for f in sorted(SAMPLES.glob("*.txt")):
        add_doc(f.stem, f.read_text(encoding="utf-8"))
    port = int(os.environ.get("PORT", 8000))
    llm = LLM()
    print(f"[anonymiser] model={llm.model} endpoint={llm.base_url}", flush=True)
    print(f"[anonymiser] review screen: http://localhost:{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
