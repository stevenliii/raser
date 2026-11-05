#!/bin/bash
# Download the full competition dataset into data/. It's about 21 GB.
#SBATCH --job-name=raser-download
#SBATCH --partition=ice-cpu
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=03:00:00
#SBATCH --output=results/slurm/%x-%j.out
set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
source .venv/bin/activate
python scripts/download_data.py --all
