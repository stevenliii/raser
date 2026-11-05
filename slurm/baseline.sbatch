#!/bin/bash
# Experiment 1: frozen Gemma on the valid tasks. Resubmit to resume.
# Full run, one job per seed:   sbatch --array=1-3 slurm/baseline.sbatch
# One-task test:                RUN_NAME=smoke sbatch slurm/baseline.sbatch --limit 1
# Extra arguments go to run_eval.py. Change the GPU with sbatch --gres=gpu:<type>:1, but
# keep it NVIDIA: ice-gpu also has AMD cards (mi210, r9700), which this vLLM can't use.
#SBATCH --job-name=raser-baseline
#SBATCH --partition=ice-gpu
#SBATCH --gres=gpu:a100:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=96G
#SBATCH --time=16:00:00
#SBATCH --output=results/slurm/%x-%j.out
set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
source .venv/bin/activate
source scripts/podman_env.sh
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv

MODEL=gemma-4-12b-it-qat-w4a16-ct
SEED="${SLURM_ARRAY_TASK_ID:-1}"
python scripts/run_eval.py \
  --run-name "${RUN_NAME:-baseline_12b_seed${SEED}}" \
  --seed "$SEED" \
  --model-path "models/$MODEL" \
  --task-envs envs \
  --task-list tasks/valid_tasks.json \
  --concurrency "${CONCURRENCY:-4}" \
  --port $((8000 + SEED)) \
  "$@"
