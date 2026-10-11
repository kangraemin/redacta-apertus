.PHONY: run eval eval-all benchmark model stop

GGUF_FILE ?= apertus-v1.5-8b-text-q4_k_m.gguf
export GGUF_FILE

# make run: start the review screen on http://localhost:8000
#  - with LLM_BASE_URL / LLM_NAME / LLM_API_KEY set, it uses that Apertus endpoint;
#  - without them, it starts Apertus itself from ./models (air-gapped mode, see `make model`).
run:
	@mkdir -p outputs
	@if [ -n "$$LLM_BASE_URL" ]; then \
		echo "Using Apertus endpoint $$LLM_BASE_URL ($$LLM_NAME)"; \
		docker compose up --build app; \
	else \
		if [ ! -f models/$(GGUF_FILE) ]; then \
			echo "No LLM_BASE_URL set and models/$(GGUF_FILE) missing."; \
			echo "Either export LLM_BASE_URL/LLM_NAME/LLM_API_KEY, or run 'make model' once (needs internet) for air-gapped mode."; \
			exit 1; \
		fi; \
		echo "Air-gapped mode: Apertus runs from models/$(GGUF_FILE) on an internal Docker network"; \
		LLM_BASE_URL= docker compose --profile airgap up --build; \
	fi

# Measure accuracy on the benchmark (test split). Results land in outputs/eval_<mode>/.
# Uses LLM_BASE_URL if set, otherwise starts the local Apertus container (air-gapped mode).
EVAL_RUN = docker compose $(if $(LLM_BASE_URL),,--profile airgap) run --rm --build -e LLM_CACHE_DIR=/app/outputs/llm_cache app

eval:
	@mkdir -p outputs
	@if [ -z "$$LLM_BASE_URL" ]; then LLM_BASE_URL= docker compose --profile airgap up -d apertus; fi
	$(EVAL_RUN) python -m src.evaluate --mode full --split test --out outputs/eval_full $(EVAL_ARGS)

eval-all:
	@mkdir -p outputs
	@if [ -z "$$LLM_BASE_URL" ]; then LLM_BASE_URL= docker compose --profile airgap up -d apertus; fi
	$(EVAL_RUN) python -m src.evaluate --mode rules --out outputs/eval_rules
	$(EVAL_RUN) python -m src.evaluate --mode full --out outputs/eval_full
	$(EVAL_RUN) python -m src.evaluate --mode apertus --out outputs/eval_apertus

# Rebuild the benchmark from the downloaded decisions (data/raw -> data/benchmark).
benchmark:
	python3 -m src.build_benchmark --raw data/raw --out data/benchmark --seed 7

# Build time only: fetch Apertus weights for air-gapped mode. See docs/model.md.
model:
	@sh scripts/get_model.sh $(GGUF_FILE)

stop:
	docker compose --profile airgap down
