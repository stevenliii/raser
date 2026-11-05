#!/usr/bin/env python
"""Run one evaluation under the same harness settings as Kaggle's starter notebook.

Use this instead of `swegemma eval`, which ignores eval_config.yaml and leaves out
context compaction and caching.

Modes:
  agent      run the agent and grade its patches
  reference  grade each task's reference patch (no model needed)
  empty      grade an empty patch (no model needed)

Rerunning the same --run-name resumes it. Each attempt writes to its own part-NNN
folder because the harness overwrites a results folder when a run finishes.
"""
from __future__ import annotations

import argparse
import asyncio
import contextvars
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

os.environ.update(
    TRANSFORMERS_NO_TF='1',
    TRANSFORMERS_NO_FLAX='1',
    TRANSFORMERS_OFFLINE='1',
    VLLM_NO_USAGE_STATS='1',
    VLLM_WORKER_MULTIPROC_METHOD='spawn',
    VLLM_ENGINE_READY_TIMEOUT_S='1200',
    PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True',
    LITELLM_LOCAL_MODEL_COST_MAP='True',
    LITELLM_TELEMETRY='False',
    LITELLM_LOG='WARNING',
    OTEL_SDK_DISABLED='true',
)

import litellm  # noqa: E402
import yaml  # noqa: E402
from adk_eval_core.tracing import SessionTrace  # noqa: E402
from adk_submission import ModelRegistry, discover_adapters, validate_directory  # noqa: E402
from adk_submission.discovery import discover_declared_models  # noqa: E402
from adk_submission.resolvers.generation import install_litellm_reasoning_patch  # noqa: E402
from google.adk.agents.context_cache_config import ContextCacheConfig  # noqa: E402
from google.adk.apps._configs import EventsCompactionConfig  # noqa: E402
from google.adk.models.lite_llm import LiteLlm  # noqa: E402
from swegemma.config import EvalConfig, build_submission_limits  # noqa: E402
from swegemma.evaluate import Evaluator  # noqa: E402
from swegemma.harness import container_setup  # noqa: E402
from swegemma.models import load_tasks  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_MODELS = {
    'gemma-4-31b-it-qat-w4a16-ct',
    'gemma-4-12b-it-qat-w4a16-ct',
    'gemma-4-e4b-it-qat-w4a16-ct',
    'gemma-4-e2b-it-qat-w4a16-ct',
}
VLLM_EXTRA_ARGS = {
    'gemma-4-12b-it-qat-w4a16-ct': (
        '--hf-overrides',
        '{"architectures": ["Gemma4ForCausalLM"], "model_type": "gemma4"}',
    ),
}


CURRENT_TASK: contextvars.ContextVar[str] = contextvars.ContextVar('current_task')


class TaskEvaluator(Evaluator):
    """Record which task is running, so sandbox setup can find that task's packages."""

    async def evaluate_task(self, task, *args, **kwargs):
        token = CURRENT_TASK.set(task.instance_id)
        try:
            return await super().evaluate_task(task, *args, **kwargs)
        finally:
            CURRENT_TASK.reset(token)


class ReferencePatchEvaluator(TaskEvaluator):
    """Skip the agent and grade the task's reference patch with the real verifier."""

    async def _run_agent_sandbox(self, task, snapshot_path, task_index, total_tasks, **kwargs):
        return task.patch, None, SessionTrace()


def use_task_envs(env_dir: Path) -> None:
    """Replace the harness's one-size-fits-all wheel step with the task's own archive."""

    def install(docker, container_id, repo, config=None):
        archive = env_dir / f'{CURRENT_TASK.get()}.tar'
        if not archive.exists():
            raise FileNotFoundError(f'No package archive for this task: {archive}')
        container_setup._extract_tar_into_site_packages(docker, container_id, archive)

    container_setup._ensure_container_site_packages = install


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('--run-name', required=True)
    parser.add_argument('--mode', choices=['agent', 'reference', 'empty'], default='agent')
    parser.add_argument('--agent', type=Path, default=ROOT / 'agents/gemma_baseline')
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    parser.add_argument('--results-dir', type=Path, default=ROOT / 'results')
    parser.add_argument('--seed', type=int, default=None, help='Sampling seed')
    parser.add_argument('--sandbox', choices=['docker', 'subprocess'], default='docker')
    parser.add_argument('--image', default='swebench-sandbox:latest', help='Docker sandbox image')
    parser.add_argument('--task-envs', type=Path, help='Folder from build_task_envs.py')
    parser.add_argument('--concurrency', type=int, default=1)
    parser.add_argument('--task-ids', nargs='+', help='Only these tasks')
    parser.add_argument('--task-list', type=Path, help='JSON list of task ids to run')
    parser.add_argument('--repos', nargs='+', help='Only these repos, such as psf/requests')
    parser.add_argument('--limit', type=int, help='Only the first N selected tasks')
    server = parser.add_mutually_exclusive_group()
    server.add_argument('--model-path', type=Path, help='Weights directory; starts vLLM')
    server.add_argument('--endpoint', help='Use a running OpenAI-compatible server')
    parser.add_argument('--gpus', type=int, help='GPUs for vLLM; defaults to all visible')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument(
        '--speculative-ngram', type=int, metavar='N',
        help='Propose N tokens by matching text already in the prompt (vLLM n-gram speculative decoding)',
    )
    args = parser.parse_args()
    if args.mode == 'agent' and not (args.model_path or args.endpoint):
        parser.error('agent mode needs --model-path or --endpoint')
    return args


def prepare_agent(source: Path, run_dir: Path, seed: int | None) -> Path:
    """Copy the agent so each run records exactly what it used, including its seed."""
    agent_dir = run_dir / 'agent'
    if agent_dir.exists():
        shutil.rmtree(agent_dir)
    shutil.copytree(source, agent_dir)
    if seed is not None:
        sampling_path = agent_dir / 'configs' / 'sampling.yaml'
        sampling = yaml.safe_load(sampling_path.read_text(encoding='utf-8'))
        sampling['seed'] = seed
        sampling_path.write_text(yaml.safe_dump(sampling, sort_keys=False), encoding='utf-8')
    return agent_dir


def select_tasks(args: argparse.Namespace, run_dir: Path) -> tuple[list[str], int]:
    """Return unfinished task ids and how many earlier attempts exist."""
    tasks = load_tasks(args.data_dir / 'tasks.jsonl')
    if args.task_ids:
        known = {t.instance_id for t in tasks}
        missing = sorted(set(args.task_ids) - known)
        if missing:
            sys.exit(f'Unknown task ids: {missing}')
        tasks = [t for t in tasks if t.instance_id in set(args.task_ids)]
    if args.task_list:
        allowed = set(json.loads(args.task_list.read_text(encoding='utf-8')))
        tasks = [t for t in tasks if t.instance_id in allowed]
    if args.repos:
        tasks = [t for t in tasks if t.repo in set(args.repos)]
    if args.limit:
        tasks = tasks[: args.limit]

    parts = sorted(run_dir.glob('part-*'))
    finished: set[str] = set()
    for part in parts:
        results = part / 'task_results.jsonl'
        if results.exists():
            with open(results, encoding='utf-8') as f:
                finished |= {json.loads(line)['instance_id'] for line in f if line.strip()}
    return [t.instance_id for t in tasks if t.instance_id not in finished], len(parts)


def speculative_config(args: argparse.Namespace) -> dict | None:
    if not args.speculative_ngram:
        return None
    return {'method': 'ngram', 'num_speculative_tokens': args.speculative_ngram, 'prompt_lookup_max': 4}


def build_models(args: argparse.Namespace, agent_dir: Path, model: str, log_path: Path):
    """Return (model registry, adapters, running vLLM server or None)."""
    adapters = discover_adapters(str(agent_dir))
    if args.mode != 'agent':
        return ModelRegistry(), adapters, None
    if args.endpoint:
        models = ModelRegistry()
        models.register(
            model,
            LiteLlm(model=f'openai/{model}', api_base=args.endpoint, api_key='EMPTY', num_retries=3),
        )
        return models, adapters, None

    import torch
    from adk_submission import VllmConfig, VllmServer

    gpus = args.gpus or torch.cuda.device_count()
    if gpus not in (1, 2, 4):
        sys.exit(f'vLLM tensor parallelism expects 1, 2 or 4 GPUs, found {gpus}')
    adapter_map = getattr(adapters, 'adapters', None) or {}
    ranks = [r for info in adapter_map.values() if (r := getattr(info, 'rank', None))]
    config = VllmConfig(
        model=str(args.model_path),
        port=args.port,
        host='127.0.0.1',
        tool_call_parser='gemma4',
        reasoning_parser='gemma4',
        max_model_len=32768,
        dtype='bfloat16' if torch.cuda.is_bf16_supported() else 'auto',
        gpu_memory_utilization=0.90,
        enable_auto_tool_choice=True,
        enable_lora=bool(adapter_map),
        max_loras=max(1, len(adapter_map)),
        max_lora_rank=max(ranks) if ranks else 128,
        scheduler_reserve_full_isl=False,
        tensor_parallel_size=gpus,
        startup_timeout=60 * 20,
        extra_args=VLLM_EXTRA_ARGS.get(model, ()),
        speculative_config=speculative_config(args),
    )
    server = VllmServer(config, adapter_manifest=adapters)
    # Write vLLM's log, including its throughput and cache statistics, into the run folder.
    # The harness otherwise writes it to a temporary file and deletes it on stop.
    Path(server.log_path).unlink(missing_ok=True)
    server.log_path = str(log_path)
    server.start()
    models = server.create_model_registry(aliases=[model], model_prefix='openai/', api_key='EMPTY')
    return models, adapters, server


def main() -> None:
    args = parse_args()
    run_dir = args.results_dir / args.run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    if args.sandbox == 'subprocess':
        print(
            'WARNING: the subprocess sandbox skips test dependency installation and imports '
            "packages from this Python environment, so correct patches can fail. Don't report these results.",
            file=sys.stderr,
        )

    task_ids, attempts = select_tasks(args, run_dir)
    if not task_ids:
        print(f'{args.run_name}: all selected tasks are finished')
        return
    print(f'{args.run_name}: {len(task_ids)} tasks to run, {attempts} earlier attempts')

    agent_dir = prepare_agent(args.agent, run_dir, args.seed)
    limits, generation_constraints = build_submission_limits()
    validate_directory(agent_dir, limits=limits)
    declared = discover_declared_models(agent_dir)
    if len(declared) != 1 or not declared <= ALLOWED_MODELS:
        sys.exit(f'Agent must declare exactly one allowed model, found {sorted(declared)}')
    model = next(iter(declared))

    budgets = yaml.safe_load((agent_dir / 'eval_config.yaml').read_text(encoding='utf-8'))['evaluation']
    part_dir = run_dir / f'part-{attempts + 1:03d}'
    commit = subprocess.run(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.strip()
    dirty = subprocess.run(
        ['git', 'status', '--porcelain'], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.strip()
    part_dir.mkdir()
    (part_dir / 'run.json').write_text(
        json.dumps(
            {
                'started': datetime.now(timezone.utc).isoformat(),
                'argv': sys.argv,
                'git_commit': commit,
                'git_dirty': bool(dirty),
                'model': model,
                'seed': args.seed,
                'mode': args.mode,
                'sandbox': args.sandbox,
                'image': args.image,
                'task_envs': str(args.task_envs) if args.task_envs else None,
                'budgets': budgets,
                'speculative_config': speculative_config(args),
                'tasks': task_ids,
                'host': platform.node(),
                'versions': {p: version(p) for p in ('swegemma', 'adk-submission', 'google-adk')},
            },
            indent=2,
        ),
        encoding='utf-8',
    )

    litellm.drop_params = True
    install_litellm_reasoning_patch()
    models, adapters, server = build_models(args, agent_dir, model, part_dir / 'vllm.log')
    config = EvalConfig(
        tasks_path=args.data_dir / 'tasks.jsonl',
        snapshots_dir=args.data_dir / 'snapshots',
        results_dir=part_dir,
        submission_dir=agent_dir,
        models=models,
        sandbox=args.sandbox,
        image=args.image,
        timeout_seconds=int(budgets['timeout_seconds']),
        verification_timeout_seconds=300,
        max_time_minutes=float(budgets['max_time_minutes']),
        max_tool_calls=int(budgets['max_tool_calls']),
        max_turns=int(budgets['max_turns']),
        limits=limits,
        generation_constraints=generation_constraints,
        adapter_manifest=adapters,
        context_cache_config=ContextCacheConfig(min_tokens=2048, ttl_seconds=1800, cache_intervals=10),
        events_compaction_config=EventsCompactionConfig(
            compaction_interval=15,
            overlap_size=2,
            token_threshold=14336,
            event_retention_size=5,
        ),
        graph_dir=str(args.data_dir / 'graphs'),
        embeddings_dir=str(args.data_dir / 'embeddings'),
        wheels_dir=args.data_dir / 'wheels',
        task_ids=task_ids,
        skip_agent_patch=args.mode == 'empty',
        concurrency=args.concurrency,
        display_mode='quiet',
    )
    if args.task_envs:
        use_task_envs(args.task_envs.resolve())
    evaluator_class = ReferencePatchEvaluator if args.mode == 'reference' else TaskEvaluator
    try:
        result = asyncio.run(evaluator_class(config).run())
    finally:
        if server is not None:
            server.log_path = None  # keep the log: stop() deletes the file at log_path
            server.stop()
    print(f'{args.run_name}: {result.resolved}/{result.total} resolved in this attempt')


if __name__ == '__main__':
    main()
