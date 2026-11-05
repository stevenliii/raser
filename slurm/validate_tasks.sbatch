#!/bin/bash
# Grade reference and empty patches for all tasks. Resubmit to resume. No GPU needed.
#SBATCH --job-name=raser-validate
#SBATCH --partition=ice-cpu
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=04:00:00
#SBATCH --output=results/slurm/%x-%j.out
set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
source .venv/bin/activate
source scripts/podman_env.sh
python scripts/run_eval.py --run-name validate_reference --mode reference --concurrency 8
python scripts/run_eval.py --run-name validate_empty --mode empty --concurrency 8
