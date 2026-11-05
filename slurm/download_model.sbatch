#!/bin/bash
# Download Gemma weights into models/. Extra arguments go to download_model.py,
# such as --name gemma-4-e4b-it-qat-w4a16-ct.
#SBATCH --job-name=raser-model
#SBATCH --partition=ice-cpu
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --output=results/slurm/%x-%j.out
set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
source .venv/bin/activate
python scripts/download_model.py "$@"
