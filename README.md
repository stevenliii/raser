# raser

CS 4644/7643 project: structured state representations for RL-trained, local software engineering agents, built on the [Gemma 4 Developer Agent Competition](https://www.kaggle.com/competitions/gemma-4-developer-agent).

## Setup

You need [uv](https://docs.astral.sh/uv/), Docker, and the Kaggle CLI logged in with an account that has joined the competition.

```bash
scripts/setup_env.sh
source .venv/bin/activate
python scripts/download_data.py --task-ids rich_3278 rich_3521
scripts/build_sandbox.sh
```

Only download the full dataset on PACE ICE, using `python scripts/download_data.py --all`. It's about 21 GB, and extracting it can briefly need about twice that, so keep it in scratch. Laptops only need the few tasks above for small tests.

On a Linux machine with NVIDIA GPUs, use `scripts/setup_env.sh --gpu` to install vLLM as well.

## Check the sandbox

Grading a task's reference patch should pass, and grading an empty patch should fail. This needs no model.

```bash
python scripts/run_eval.py --run-name validate_reference --mode reference --task-ids rich_3278 rich_3521
python scripts/run_eval.py --run-name validate_empty --mode empty --task-ids rich_3278 rich_3521
```

Run both on all tasks before reporting results. Omit `--task-ids` to do that.

## Experiment 1: Gemma baseline

The agent is in `agents/gemma_baseline/`: frozen Gemma 4, the raw text transcript, all nine harness tools, and no adapters or sub-agents.

```bash
python scripts/run_eval.py --run-name baseline_12b_seed1 --seed 1 \
  --model-path models/gemma-4-12b-it-qat-w4a16-ct --concurrency 4
```

Use `--endpoint http://host:port/v1` instead of `--model-path` to use a server that is already running. Rerun the same `--run-name` to resume.

Always use `scripts/run_eval.py` rather than `swegemma eval`, because the CLI ignores `eval_config.yaml` and leaves out context compaction and caching.

## Results

```bash
python scripts/summarize.py results/baseline_12b_seed* \
  --valid-from results/validate_reference --invalid-from results/validate_empty \
  --csv results/baseline_12b_per_task.csv
```

This reports resolution rate and tool calls for each run, and a bootstrap interval across tasks. To make a Kaggle submission, run `python scripts/package_submission.py --agent agents/gemma_baseline`.

## Known issues

- **Subprocess sandbox:** `--sandbox subprocess` skips test dependency installation and imports packages from the harness environment, so correct patches can fail. Use it only to debug the harness.
- **PACE ICE:** PACE has no Docker, so jobs source `scripts/podman_env.sh` to get a Docker-compatible Podman socket. Test it with `mkdir -p results/slurm && sbatch slurm/test_sandbox.sbatch`.
- **Kept out of Git:** `data/`, `vendor/`, `models/`, `results/` and submission zips.
