#!/bin/bash
# Grade reference and empty patches for all tasks. Resubmit to resume. No GPU needed.
# Build envs/ first with slurm/build_task_envs.sbatch.
#SBATCH --job-name=raser-validate
#SBATCH --partition=ice-cpu
#SBATCH --cpus-per-task=16
#SBATCH --mem=96G
#SBATCH --time=04:00:00
#SBATCH --output=results/slurm/%x-%j.out
set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
source .venv/bin/activate
source scripts/podman_env.sh
python scripts/run_eval.py --run-name validate_reference --mode reference --task-envs envs --concurrency 8
python scripts/run_eval.py --run-name validate_empty --mode empty --task-envs envs --concurrency 8
