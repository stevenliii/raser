#!/usr/bin/env bash
# Create .venv with the competition harness.
#   scripts/setup_env.sh        harness only (laptop)
#   scripts/setup_env.sh --gpu  also installs vLLM (Linux with NVIDIA GPUs)
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"

# On PACE, keep the repo and uv's cache out of the small home quota.
if [[ -e "$HOME/scratch" ]]; then
  export UV_CACHE_DIR="${UV_CACHE_DIR:-$HOME/scratch/.cache/uv}"
  case "$(pwd -P)/" in
    "$(cd "$HOME/scratch" && pwd -P)"/*) ;;
    *) echo "Move this repo to ~/scratch first: home is too small for it." >&2; exit 1 ;;
  esac
fi

for tool in uv kaggle; do
  command -v "$tool" >/dev/null || { echo "$tool is not installed. See README.md." >&2; exit 1; }
done

DATASET=metric/gemma-4-developer-agent-wheelhouse
wheels=(swegemma-0.2.11-py3-none-any.whl adk_submission-0.2.13-py3-none-any.whl adk_eval_core-0.1.0-py3-none-any.whl)
gpu_pins=()
if [[ "${1:-}" == "--gpu" ]]; then
  wheels+=(vllm-0.19.1-cp38-abi3-manylinux_2_31_x86_64.whl)
  # Newer transformers makes vLLM crash at startup, and newer fastapi breaks the
  # instrumentator version that google-adk's starlette pin allows, failing health checks.
  gpu_pins=("transformers==5.13.1" "tokenizers==0.22.2" "compressed-tensors==0.15.0.1"
            "safetensors==0.8.0" "mistral-common==1.11.7" "fastapi==0.136.1")
fi

mkdir -p vendor/wheels
for w in "${wheels[@]}"; do
  [[ -f "vendor/wheels/$w" ]] || kaggle datasets download "$DATASET" -f "$w" -p vendor/wheels
done

uv venv --python 3.12 --allow-existing .venv
# litellm 1.108 fails against mcp 1.30 on every model call, so keep this pin.
uv pip install --python .venv/bin/python "${wheels[@]/#/vendor/wheels/}" \
  "google-adk==1.36.1" "google-genai==2.11.0" "litellm==1.76.0" ${gpu_pins[@]+"${gpu_pins[@]}"}
.venv/bin/python -c "import swegemma, adk_submission; print('Harness installed')"
