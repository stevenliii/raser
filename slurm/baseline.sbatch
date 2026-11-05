#!/bin/bash
# Experiment 1: frozen Gemma on the valid tasks. Resubmit to resume.
# Full run, one job per seed:   sbatch --array=1-3 slurm/baseline.sbatch
# One-task test:                RUN_NAME=smoke sbatch -t 00:45:00 slurm/baseline.sbatch --limit 1
# Extra arguments go to run_eval.py. Change the GPU with sbatch --gres=gpu:<type>:1.
# Use h100, h200, a100, l40s or a40. Not v100 or rtx_6000: the model needs bfloat16.
# Not mi210 or r9700: they're AMD cards.
#SBATCH --job-name=raser-baseline
#SBATCH --partition=ice-gpu
#SBATCH --gres=gpu:a100:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=96G
#SBATCH --time=08:00:00
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
