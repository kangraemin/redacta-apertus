#!/bin/sh
# Build-time only (needs internet once). Puts an Apertus v1.5 8B GGUF into ./models
# so that `make run` can work without any network afterwards.
#
# Option A (default): download a ready text-only GGUF from Hugging Face.
#   The Apertus repos are gated (accept the licence once on the model page), so set HF_TOKEN.
# Option B: build the GGUF yourself from the official weights: scripts/convert_gguf.sh
set -e
FILE=${1:-apertus-v1.5-8b-text-q4_k_m.gguf}
mkdir -p models
if [ -f "models/$FILE" ]; then echo "models/$FILE already there"; exit 0; fi
if [ -z "$HF_TOKEN" ]; then
  echo "Set HF_TOKEN (Hugging Face token with the Apertus licence accepted), or run scripts/convert_gguf.sh"; exit 1
fi
case "$FILE" in
  *q8_0*) REPO=andreasmartin/apertus-v1.5-8b-text-Q8_0-GGUF; SRC=apertus-v1.5-8b-text-q8_0.gguf ;;
  *)      REPO=Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF;     SRC=apertus-v1.5-8b-text-q4_k_m.gguf ;;
esac
echo "Downloading $REPO/$SRC -> models/$FILE"
curl -fL -H "Authorization: Bearer $HF_TOKEN" -o "models/$FILE" "https://huggingface.co/$REPO/resolve/main/$SRC"
echo "done. Now: make run"
