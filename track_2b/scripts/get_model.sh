#!/bin/sh
# Build-time only (needs internet once). Puts an Apertus v1.5 8B GGUF into ./models
# so that `make run` can work without any network afterwards.
#
# Option A (default): download a ready text-only GGUF from Hugging Face (public, no token needed;
#   HF_TOKEN is used if set). By downloading you accept the Apertus licence and acceptable use policy.
# Option B: build the GGUF yourself from the official weights: scripts/convert_gguf.sh
set -e
FILE=${1:-apertus-v1.5-8b-text-q4_k_m.gguf}
mkdir -p models
if [ -f "models/$FILE" ]; then echo "models/$FILE already there"; exit 0; fi
case "$FILE" in
  *q8_0*) REPO=andreasmartin/apertus-v1.5-8b-text-Q8_0-GGUF; SRC=apertus-v1.5-8b-text-q8_0.gguf ;;
  *)      REPO=Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF;     SRC=apertus-v1.5-8b-text-q4_k_m.gguf ;;
esac
echo "Downloading $REPO/$SRC -> models/$FILE"
AUTH=""; [ -n "$HF_TOKEN" ] && AUTH="Authorization: Bearer $HF_TOKEN"
curl -fL ${AUTH:+-H "$AUTH"} -o "models/$FILE" "https://huggingface.co/$REPO/resolve/main/$SRC"
echo "done. Now: make run"
