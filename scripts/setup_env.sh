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
if [[ "${1:-}" == "--gpu" ]]; then
  wheels+=(vllm-0.19.1-cp38-abi3-manylinux_2_31_x86_64.whl)
fi

mkdir -p vendor/wheels
for w in "${wheels[@]}"; do
  [[ -f "vendor/wheels/$w" ]] || kaggle datasets download "$DATASET" -f "$w" -p vendor/wheels
done

uv venv --python 3.12 --allow-existing .venv
# litellm 1.108 fails against mcp 1.30 on every model call, so keep this pin.
uv pip install --python .venv/bin/python "${wheels[@]/#/vendor/wheels/}" \
  "google-adk==1.36.1" "google-genai==2.11.0" "litellm==1.76.0"
.venv/bin/python -c "import swegemma, adk_submission; print('Harness installed')"
