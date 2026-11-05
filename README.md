# raser

Structured state representations for RL-trained, local software engineering agents, built on the [Gemma 4 Developer Agent Competition](https://www.kaggle.com/competitions/gemma-4-developer-agent).

## Where things run

| Work | Where |
|---|---|
| Writing code, small tests, building the sandbox image | Laptop with Docker |
| Full dataset, model weights, validation, experiments | PACE ICE, in scratch |

Only download the full dataset and model weights on PACE.

## Before you start

- Accept the [competition rules](https://www.kaggle.com/competitions/gemma-4-developer-agent/rules) with your own Kaggle account.
- Create a Kaggle API token and save it as `~/.kaggle/kaggle.json`, with permissions set to `600`.
- Install [uv](https://docs.astral.sh/uv/) and the Kaggle CLI (`uv tool install kaggle`) on your laptop.

## 1. Build the sandbox image on your laptop

PACE has no Docker, and building the image with Podman there fails, so build it on a laptop with Docker running:

```bash
scripts/setup_env.sh
source .venv/bin/activate
python scripts/download_data.py --task-ids rich_3278 rich_3521
scripts/build_sandbox.sh
```

This saves the image to `data/sandbox_image.tar`. Build it once again after any change to `docker/Dockerfile`.

## 2. Set up PACE ICE

Connect through the GT VPN first. Keep the repo in scratch, not home. Home is limited to 30 GB and scratch to 300 GB. The course's PACE guide also lists a maximum of 8 hours, 16 GPU hours and 512 CPU hours per job. Students shouldn't contact PACE support directly, so post questions in the course thread. Scratch can be purged after a period of inactivity, so keep important results somewhere else too.

**On PACE:**

```bash
cat >> ~/.bashrc <<'BASHRC'
export UV_CACHE_DIR=~/scratch/.cache/uv
export PATH="$HOME/.local/bin:$PATH"
BASHRC
source ~/.bashrc

curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install kaggle

cd ~/scratch
git clone https://github.com/stevenliii/raser.git
cd raser
mkdir -p data results/slurm ~/.kaggle
```

**On your laptop,** copy your Kaggle token and the sandbox image, replacing `<username>`:

```bash
scp ~/.kaggle/kaggle.json <username>@login-ice.pace.gatech.edu:~/.kaggle/
scp data/sandbox_image.tar <username>@login-ice.pace.gatech.edu:~/scratch/raser/data/
```

**On PACE,** install the harness and vLLM, then download the data and weights:

```bash
chmod 600 ~/.kaggle/kaggle.json
scripts/setup_env.sh --gpu
source .venv/bin/activate
sbatch slurm/download_data.sbatch
sbatch slurm/download_model.sbatch
```

Check jobs with `squeue -u $USER`. Logs are in `results/slurm/`. When both downloads finish, `ls data/snapshots | wc -l` should print `129`, and `models/gemma-4-12b-it-qat-w4a16-ct/` should contain `model.safetensors`. If the dataset download fails, `data_install_instructions.md` describes a manual `curl` method. It uses a different folder layout, so move the files up into `data/` if you use it.

## 3. Validate the tasks

The harness installs one set of package versions for every task, which breaks tasks from different commits. `scripts/build_task_envs.py` instead builds a package archive for each task from its own requirements, using versions available on the task's date. A valid task is one where the reference patch passes and an empty patch fails.

```bash
jid=$(sbatch --parsable slurm/build_task_envs.sbatch)
sbatch --dependency=afterok:$jid slurm/validate_tasks.sbatch
```

When both jobs finish:

```bash
python scripts/validation_report.py --write-valid tasks/valid_tasks.json
```

`tasks/valid_tasks.json` is in the repo and currently lists 112 tasks: 61 fastapi, 45 rich, 5 requests and 1 httpx. Rerunning `validate_tasks.sbatch` skips finished tasks, so move or delete `results/validate_reference` and `results/validate_empty` for a fresh run. `envs/manifest.json` records whether each task used its date cutoff or needed a fallback.

For a quick check on two tasks, build their environments, then run the sandbox test:

```bash
python scripts/build_task_envs.py --task-ids rich_3278 rich_3521
sbatch slurm/test_sandbox.sbatch
```

The job's log should end with `2/2 resolved` for the reference patch and `0/2 resolved` for the empty patch.

## 4. Experiment 1: Gemma baseline

The agent is in `agents/gemma_baseline/`: frozen Gemma 4, the raw text transcript, all nine harness tools, and no adapters or sub-agents.

Test one task first:

```bash
CONCURRENCY=1 RUN_NAME=smoke sbatch -t 00:45:00 slurm/baseline.sbatch --limit 1
```

Then run the full baseline, with one job per seed:

```bash
sbatch --array=1-3 slurm/baseline.sbatch
```

Results go to `results/baseline_12b_calls50_seed<N>`. Each seed is a repeat of the same run. The model samples its answers, so the same agent solves different tasks on different runs, and three seeds show how much of a difference is chance.

Runs end at 50 tool calls, with a 15-minute time limit only as a safety net. A tool call limit means the same thing on any GPU, while real time depends on the GPU and on how many tasks share it. At about 8 seconds per model call, a seed should take about 3–4 hours. Keep the GPU type, `CONCURRENCY` and limits the same across experiments you compare anyway.

To check on running jobs:

```bash
squeue -u $USER
for s in 1 2 3; do echo "seed $s: $(cat results/baseline_12b_calls50_seed$s/part-*/task_results.jsonl 2>/dev/null | wc -l)/112"; done
python scripts/summarize.py results/baseline_12b_calls50_seed*
```

The counts should rise to `112` and `errors` should stay at `0`. `budget` counts runs that hit the time or tool call limit, which is normal. If a seed leaves `squeue` before reaching `112`, resume it with `sbatch -t 06:00:00 --array=<seed> slurm/baseline.sbatch`.

Each attempt's folder has `vllm.log`, which reports vLLM's throughput and prefix cache hit rate every few seconds:

```bash
grep "throughput" results/<run>/part-001/vllm.log | tail -5
```

### Speculative decoding

`--speculative-ngram 4` turns on vLLM's n-gram speculative decoding, which guesses up to 4 tokens by matching text already in the prompt and keeps only what the model would have produced. It should speed up output that copies from the code, without changing what the agent does. Test it on a few tasks before using it for a full run, and use the same setting for every run you compare:

```bash
RUN_NAME=spec_off sbatch -t 01:00:00 slurm/baseline.sbatch --limit 5
RUN_NAME=spec_on sbatch -t 01:00:00 slurm/baseline.sbatch --limit 5 --speculative-ngram 4 --port 8011
```

The second job uses another port in case both land on the same node. Compare the generation throughput in each run's `vllm.log`, and `duration_seconds` and `tool_calls` in `task_results.jsonl`. Five tasks is a small sample, so look for a large difference.

The job asks for one A100. To use another GPU, add `--gres=gpu:<type>:1`, such as `h100`, `h200`, `l40s` or `a40`. Don't use `v100`, which doesn't support the `bfloat16` format this model needs, and `rtx_6000` has the same limitation as far as we know. Don't use `mi210` or `r9700`, which are AMD cards. If a job waits for a long time, ask for less: a shorter time limit with `-t`, and fewer CPUs with `-c 8 --mem=64G` and `CONCURRENCY=1`. Resubmit a job to resume it.

Always use `scripts/run_eval.py` rather than `swegemma eval`, because the CLI ignores `eval_config.yaml` and leaves out context compaction and caching.

## 5. Results

```bash
python scripts/summarize.py results/baseline_12b_calls50_seed* \
  --valid-from results/validate_reference --invalid-from results/validate_empty \
  --csv results/baseline_12b_calls50_per_task.csv
```

This reports resolution rate and tool calls for each run, and a bootstrap interval across tasks. To make a Kaggle submission, run `python scripts/package_submission.py --agent agents/gemma_baseline`.

### Saving runs

Scratch can be purged, so archive each finished run in `reports/`. On PACE:

```bash
mkdir -p results/saved
tar -czf results/saved/baseline_12b_seed1.tar.gz -C results baseline_12b_seed1
```

Then on your laptop:

```bash
scp <username>@login-ice.pace.gatech.edu:~/scratch/raser/results/saved/baseline_12b_seed1.tar.gz reports/baseline_12b/
```

Each archive has `task_results.jsonl` with one row per task, plus the agent's patches, test output and full traces. To look through one, extract it with `tar -xzf reports/baseline_12b/baseline_12b_seed1.tar.gz -C results`.

### Experiment 1 results with a 4-minute limit

Frozen Gemma 4 12B on the 112 valid tasks, with 3 seeds on one A100, 4 tasks at a time, and a 4-minute limit per task chosen to fit Kaggle's 12-hour window. These runs are named `baseline_12b_seed<N>`, and the archives are in `reports/baseline_12b/`. The rerun ending at 50 tool calls replaces them as the main baseline.

| | Seed 1 | Seed 2 | Seed 3 | Mean |
|---|---|---|---|---|
| Resolved | 24 | 19 | 20 | 21 |
| Rate | 21.4% | 17.0% | 17.9% | **18.8%** |
| Hit a budget limit | 87 | 90 | 90 | 89 |
| Errors | 0 | 0 | 0 | 0 |

The 95% bootstrap interval across tasks is 12.5% to 25.6%. By repo, `fastapi` scored 20.2% on 61 tasks, `rich` 15.6% on 45, `requests` 33.3% on 5 and `httpx` 0% on 1.

| Passed in | Tasks |
|---|---|
| 0 of 3 seeds | 84 |
| 1 of 3 | 7 |
| 2 of 3 | 7 |
| 3 of 3 | 14 |

- **Noise:** the seeds differ by up to 4.4 points with nothing changed, so a single run of a new method needs to clearly beat that.
- **Time limit:** in seed 1, 82 runs hit the 4-minute limit and 5 hit the 50-call limit. None of those 87 were resolved, while 24 of the 25 runs that finished within both limits were.
- **No patch:** in seed 1, 51 of the 112 runs ended without changing any code.
- **Training signal:** only the 14 tasks with mixed results across seeds give GRPO successes and failures to compare. Train on other tasks, such as SWE-Gym, and keep these 112 for evaluation.

## Notes for the report

- **Differences from Kaggle's setup:** the image pins pytest and puts the task's code first on `PYTHONPATH`, and tasks use per-task packages. Local scores aren't directly comparable to Kaggle's.
- **Resource limits:** Podman on PACE doesn't enforce the sandbox's 4 GB and 2 CPU limits. Network blocking works.
- **Excluded tasks:** the valid list leaves out 17 of the 129 public tasks. Many of them need network access, which the offline sandbox blocks.
- **Credit:** the diagnosis behind the per-task environments came from zbigniewkirchner's public notebook, [Do Gold Patches Pass Locally?](https://www.kaggle.com/code/zbigniewkirchner/gemma-4-agent-do-gold-patches-pass-locally).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Disk quota exceeded` during an install | Check that `UV_CACHE_DIR` points to scratch, then delete `~/.cache/uv` |
| `kaggle: command not found` | Run `source ~/.bashrc`, or install it with `uv tool install kaggle` |
| Job can't find `data/sandbox_image.tar` | Build it on your laptop and copy it to PACE |
| A job waits with `DependencyNeverSatisfied` | The job before it failed. Check its log, then `scancel` the waiting job |
| Correct patches fail with `--sandbox subprocess` | That sandbox skips test dependency installation, so use it only to debug the harness |
