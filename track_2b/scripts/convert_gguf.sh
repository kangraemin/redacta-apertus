#!/bin/sh
# How the GGUF used for our measurements was made (build time, needs internet and ~30 GB disk).
#
# Apertus v1.5 8B is an "omni" checkpoint (text + image + audio). We keep only the text branch:
#   1. download the official safetensors (swiss-ai/Apertus-v1.5-8B, gated: HF_TOKEN needed)
#   2. write a text-only config (text_config, architecture ApertusForCausalLM, vocab_size 131072)
#      and the text tokenizer (131072 tokens + special tokens)
#   3. convert with llama.cpp, keeping the first 131072 embedding rows (text vocabulary)
#   4. mark <|assistant_end|> (id 68) as end-of-generation, otherwise the model never stops
#   5. quantise to Q4_K_M
set -e
WORK=${WORK:-$HOME/apertus-convert}
mkdir -p "$WORK" models
cd "$WORK"
[ -d llama.cpp ] || git clone --depth 1 https://github.com/ggml-org/llama.cpp
python3 -m venv venv && . venv/bin/activate
pip install -q -r llama.cpp/requirements/requirements-convert_hf_to_gguf.txt huggingface_hub
hf download swiss-ai/Apertus-v1.5-8B --include "model-apertus-model-*" "*.json" "chat_template.jinja" --local-dir full
mkdir -p text
for f in full/model-apertus-model-*.safetensors; do ln -sf "$PWD/$f" text/; done
python3 - <<'PY'
import json
full = json.load(open("full/config.json"))
tc = full["text_config"]; tc["architectures"] = ["ApertusForCausalLM"]; tc["model_type"] = "apertus"; tc["vocab_size"] = 131072
json.dump(tc, open("text/config.json", "w"), indent=1)
idx = json.load(open("full/model.safetensors.index.json"))
wm = {k: v for k, v in idx["weight_map"].items() if k.startswith("model.language_model") or k == "lm_head.weight"}
json.dump({"metadata": {}, "weight_map": wm}, open("text/model.safetensors.index.json", "w"))
tok = json.load(open("full/tokenizer.json"))
tok["added_tokens"] = [t for t in tok["added_tokens"] if t["id"] < 131072]
json.dump(tok, open("text/tokenizer.json", "w"), ensure_ascii=False)
for f in ("tokenizer_config.json", "special_tokens_map.json", "generation_config.json", "chat_template.jinja"):
    open("text/" + f, "w").write(open("full/" + f).read())
# llama.cpp: keep the text rows of the embedding
p = "llama.cpp/conversion/llama.py"; s = open(p).read()
i = s.index("class ApertusModel"); a = "        yield from super().modify_tensors(data_torch, name, bid)"; j = s.index(a, i)
if "drop image/audio" not in s:
    s = s[:j] + ('        if name.endswith("embed_tokens.weight") and data_torch.shape[0] > self.hparams["vocab_size"]:\n'
                 '            data_torch = data_torch[: self.hparams["vocab_size"]]  # drop image/audio rows\n') + s[j:]
    open(p, "w").write(s)
PY
python3 llama.cpp/convert_hf_to_gguf.py text --outtype q8_0 --outfile apertus-v1.5-8b-text-q8_0.gguf
python3 llama.cpp/gguf-py/gguf/scripts/gguf_set_metadata.py apertus-v1.5-8b-text-q8_0.gguf tokenizer.ggml.eos_token_id 68 --force
llama-quantize --allow-requantize apertus-v1.5-8b-text-q8_0.gguf apertus-v1.5-8b-text-q4_k_m.gguf Q4_K_M
cd - >/dev/null
cp "$WORK/apertus-v1.5-8b-text-q4_k_m.gguf" models/
echo "models/apertus-v1.5-8b-text-q4_k_m.gguf ready"
