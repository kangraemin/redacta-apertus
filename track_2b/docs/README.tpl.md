# Redacta — anonymising Swiss court decisions with Apertus, offline

Before a Swiss court publishes a decision, a clerk replaces the parties' names with `A.________`, `B.________` and removes addresses and dates of birth. Redacta does the first pass: **Apertus v1.5 8B** and a set of rules mark what to remove, and the clerk approves or changes each mark. Everything runs on the court's own machine, with no internet connection.

![Review screen](docs/screenshot_review.png)

**Measured on {{N_TEST}} test decisions of the Federal Supreme Court (German, French, Italian)** with synthetic names put back where the court's placeholders were:

| | Redacta | Off-the-shelf NER (baseline only) | Rules only |
|---|---|---|---|
| Strings that must go, found by default | **{{R_FULL}}** | {{R_NER}} | {{R_RULES}} |
| Judge, clerk and lawyer names wrongly removed | **{{PROT_FULL}}** | {{PROT_NER}} | {{PROT_RULES}} |
| Decisions with nothing missed | {{LF_FULL}} | {{LF_NER}} | {{LF_RULES}} |
| Items for the clerk to confirm per decision | {{IC_FULL}} | {{IC_NER}} | — |

The NER baseline is spaCy `xx_ent_wiki_sm` with every person and organisation redacted; it is used only for this comparison, not in Redacta. Speed on the same ten test decisions: {{SEC10_METAL}} s per decision with Apertus on a laptop GPU (Metal), {{SEC10_CPU}} s in the CPU-only container.

Details, method and limitations: [technical report](technical_report.md) ([PDF](Redacta_Report.pdf)). Demo video: {{DEMO_URL}}

## Run it

Two ways, both with `make run` from this directory. Then open http://localhost:8000.

**1. Air-gapped (default).** Apertus runs in a llama.cpp container on a Docker network with no route to the internet. Needs the 5 GB weights in `./models` once:

```bash
make model               # build time, needs internet once: downloads models/apertus-v1.5-8b-text-q4_k_m.gguf
make run                 # from here on no network is needed
```

If the weights are missing and no endpoint is set, `make run` runs `make model` itself and then starts.
Clone into your home directory: Colima and Docker Desktop may not share paths outside it (such as `/tmp`) with containers, and the model container then finds no weights.
Without a GPU (Apertus on CPU inside Docker), the first analysis of the six sample decisions takes about 7 minutes; the page is up before that and fills in as each decision is done.

**2. Existing Apertus endpoint** (e.g. a sovereign Swiss cloud or an in-house server):

```bash
export LLM_BASE_URL=https://.../v1  LLM_NAME=swiss-ai/Apertus-v1.5-8B  LLM_API_KEY=...
make run                 # starts only the review app
```

On start the app analyses the six sample decisions in `data/sample/` (two per language). *+ Paste a decision* analyses any other text. *Approve and export* downloads the anonymised text and appends to `outputs/audit.jsonl`.

Measure accuracy yourself: `make eval-all` (rules only, Apertus only, Redacta), results in `outputs/eval_*/metrics.json`. Our results are in `docs/results/`.

## How it works

1. Apertus reads the decision in chunks of about 1,800 characters, with the list of parties as context, and returns every name with its role (party, private person, judge, lawyer, authority, ...).
2. A name is used only if Apertus copied it exactly from the text. Roles are voted over all mentions.
3. Rules catch IBAN, AHV number, phone, licence plate, date of birth and street addresses, and keep any name that follows a judge, clerk or lawyer title or sits in the bench list.
4. Each person gets a letter in order of appearance; surname-only mentions and relatives with the same surname are covered.
5. The review screen shows the decision as a page with every proposal marked, and beside it three lists: *for you to decide*, *redact* and *keep*, with the reason for each. Keys: `↓`/`↑` next and previous item, `R` redact, `K` keep, `Z` undo, `P` published text, `Shift+Enter` approve. Export is blocked until every *for you to decide* item has a decision.

![Architecture](docs/architecture.png)

## Layout

| Path | What it is |
|---|---|
| `src/anonymizer/` | pipeline, rules, Apertus client and prompt |
| `src/app.py`, `src/static/` | review server and page (Python standard library only) |
| `src/fetch_decisions.py`, `src/build_benchmark.py`, `src/evaluate.py` | data download, refilled benchmark, scoring |
| `data/raw/` | {{N_ALL}} published decisions (already anonymised by the court) |
| `data/benchmark/` | refilled benchmark with exact answer offsets |
| `data/sample/` | six refilled decisions shown on start |
| `scripts/` | model download, and how the text-only GGUF was built |
| `docs/` | report figures, results, the original challenge description |

## License

Code Apache-2.0, documentation CC-BY-4.0, data CDLA-Permissive-2.0. Built for [Hack Apertus](https://hackapertus.ch) 2026, Track 2B.
