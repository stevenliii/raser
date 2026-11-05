#!/bin/bash
# Quick check of the sandbox: both tasks should pass the reference patch and fail
# the empty patch. Needs: python scripts/download_data.py --task-ids rich_3278 rich_3521
#SBATCH --job-name=raser-test-sandbox
#SBATCH --partition=ice-cpu
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=01:00:00
#SBATCH --output=results/slurm/%x-%j.out
set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
source .venv/bin/activate
source scripts/podman_env.sh
python scripts/run_eval.py --run-name test_sandbox_reference --mode reference --task-ids rich_3278 rich_3521
python scripts/run_eval.py --run-name test_sandbox_empty --mode empty --task-ids rich_3278 rich_3521
