#!/bin/bash
# Build each task's package archive into envs/. Needs internet, but no GPU or Podman.
#SBATCH --job-name=raser-envs
#SBATCH --partition=ice-cpu
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=results/slurm/%x-%j.out
set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
export PATH="$HOME/.local/bin:$PATH"
source .venv/bin/activate
python scripts/build_task_envs.py --workers 8
