#!/usr/bin/env python
"""Summarize runs: resolution rate, tool calls and a bootstrap interval over tasks.

  summarize.py results/baseline_seed* --valid-from results/validate_reference \
      --invalid-from results/validate_empty --csv results/baseline_per_task.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path


def load_run(run_dir: Path) -> dict[str, dict]:
    """Merge a run's attempts, keeping the newest result for each task."""
    results: dict[str, dict] = {}
    for part in sorted(run_dir.glob('part-*')):
        path = part / 'task_results.jsonl'
        if path.exists():
            with open(path, encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        row = json.loads(line)
                        results[row['instance_id']] = row
    return results


def resolved_ids(run_dir: Path) -> set[str]:
    return {k for k, row in load_run(run_dir).items() if row.get('resolved')}


def bootstrap_interval(values: list[float], samples: int = 10000) -> tuple[float, float]:
    rng = random.Random(0)
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(samples))
    return means[int(0.025 * samples)], means[int(0.975 * samples)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('runs', nargs='+', type=Path)
    parser.add_argument('--valid-from', type=Path, help='Keep tasks this reference-patch run resolved')
    parser.add_argument('--invalid-from', type=Path, help='Drop tasks this empty-patch run resolved')
    parser.add_argument('--csv', type=Path, help='Write per-task pass rates here')
    args = parser.parse_args()

    runs = {run: load_run(run) for run in args.runs}
    task_ids = set().union(*runs.values())
    if args.valid_from:
        task_ids &= resolved_ids(args.valid_from)
    if args.invalid_from:
        task_ids -= resolved_ids(args.invalid_from)
    if not task_ids:
        raise SystemExit('No tasks to summarize')

    print(f'{"run":<32} {"tasks":>5} {"resolved":>8} {"rate":>6} {"budget":>6} {"errors":>6} {"calls":>6}')
    for run, results in runs.items():
        rows = [results[t] for t in task_ids if t in results]
        solved = sum(bool(r.get('resolved')) for r in rows)
        # Budget hits are the agent running out of time or tool calls. Other errors need a look.
        problems = [str(r['error']) for r in rows if r.get('error')]
        budget = sum(problem.startswith('Agent exceeded') for problem in problems)
        errors = len(problems) - budget
        calls = statistics.fmean(r.get('tool_calls') or 0 for r in rows) if rows else 0
        rate = solved / len(rows) if rows else 0
        print(f'{run.name:<32} {len(rows):>5} {solved:>8} {rate:>6.1%} {budget:>6} {errors:>6} {calls:>6.1f}')

    per_task: dict[str, list[float]] = defaultdict(list)
    repo_of: dict[str, str] = {}
    for results in runs.values():
        for task_id in task_ids:
            if task_id in results:
                per_task[task_id].append(float(bool(results[task_id].get('resolved'))))
                repo_of[task_id] = results[task_id].get('repo', '')

    rates = [statistics.fmean(v) for v in per_task.values()]
    low, high = bootstrap_interval(rates)
    print(f'\nMean per-task pass rate: {statistics.fmean(rates):.1%} (95% bootstrap CI {low:.1%} to {high:.1%})')

    by_repo: dict[str, list[float]] = defaultdict(list)
    for task_id, values in per_task.items():
        by_repo[repo_of[task_id]].append(statistics.fmean(values))
    for repo, values in sorted(by_repo.items()):
        print(f'  {repo:<24} {len(values):>4} tasks  {statistics.fmean(values):.1%}')

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with open(args.csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['instance_id', 'repo', 'runs', 'pass_rate'])
            for task_id in sorted(per_task):
                values = per_task[task_id]
                writer.writerow([task_id, repo_of[task_id], len(values), statistics.fmean(values)])
        print(f'\nWrote {args.csv}')


if __name__ == '__main__':
    main()
