#!/usr/bin/env python
"""Report which tasks are valid: the reference patch passes and the empty patch fails.

  validation_report.py [--results-dir results] [--write-valid tasks/valid_tasks.json]
"""
from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_run(run_dir: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for path in sorted(run_dir.glob('part-*/task_results.jsonl')):
        with open(path, encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    row = json.loads(line)
                    rows[row['instance_id']] = row
    return rows


def failure_causes(run_dir: Path, task_id: str) -> set[str]:
    causes: set[str] = set()
    for path in run_dir.glob(f'part-*/test_outputs/{task_id}.log'):
        text = path.read_text(encoding='utf-8', errors='ignore')
        causes |= set(re.findall(r'^E\s+(\w*(?:Error|Exception)\b.{0,90})', text, re.M))
    return causes or {'no error line'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('--results-dir', type=Path, default=ROOT / 'results')
    parser.add_argument('--reference-run', default='validate_reference')
    parser.add_argument('--empty-run', default='validate_empty')
    parser.add_argument('--envs-dir', type=Path, default=ROOT / 'envs')
    parser.add_argument('--write-valid', type=Path, help='Save the valid task ids to this JSON file')
    args = parser.parse_args()

    reference_dir = args.results_dir / args.reference_run
    reference = load_run(reference_dir)
    empty = load_run(args.results_dir / args.empty_run)
    if not reference or not empty:
        raise SystemExit(f'No results found in {args.results_dir}')

    valid = sorted(t for t, r in reference.items() if r['resolved'] and t in empty and not empty[t]['resolved'])
    print(f'Reference runs: {len(reference)}, passed: {sum(r["resolved"] for r in reference.values())}')
    print(f'Empty runs: {len(empty)}, passed: {sorted(t for t, r in empty.items() if r["resolved"])}')
    print(f'Valid tasks: {len(valid)}')

    by_repo: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    for task_id, row in reference.items():
        by_repo[row['repo']][0] += task_id in valid
        by_repo[row['repo']][1] += 1
    for repo, (good, total) in sorted(by_repo.items()):
        print(f'  {repo}: {good}/{total}')

    manifest_path = args.envs_dir / 'manifest.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        print('Environments:', dict(collections.Counter(e['status'] for e in manifest.values())))

    failed = sorted(t for t, r in reference.items() if not r['resolved'])
    causes: collections.Counter[str] = collections.Counter()
    for task_id in failed:
        causes.update(failure_causes(reference_dir, task_id))
    print('Top causes of reference failures:')
    for cause, count in causes.most_common(15):
        print(f'  {count:3d}  {cause}')
    print('Failed:', ' '.join(failed))

    if args.write_valid:
        args.write_valid.parent.mkdir(parents=True, exist_ok=True)
        args.write_valid.write_text(json.dumps(valid, indent=2) + '\n', encoding='utf-8')
        print(f'Wrote {args.write_valid}')


if __name__ == '__main__':
    main()
