#!/usr/bin/env python
"""Download competition files into data/.

  download_data.py --all                       everything (about 21 GB)
  download_data.py --task-ids httpx_3672 ...   shared files plus those tasks only
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import subprocess
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

COMP = 'gemma-4-developer-agent'
DATA = Path(__file__).resolve().parents[1] / 'data'
SHARED = ('tasks.jsonl', 'HARNESS_README.md', 'docker/', 'sandbox/', 'wheels/')


def list_files() -> list[str]:
    names: list[str] = []
    token = None
    while True:
        cmd = ['kaggle', 'competitions', 'files', COMP, '--csv', '--page-size', '200']
        if token:
            cmd += ['--page-token', token]
        out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
        lines = out.splitlines()
        token = None
        if lines and lines[0].startswith('Next Page Token'):
            token = lines.pop(0).split('=', 1)[1].strip()
        names += [row['name'] for row in csv.DictReader(io.StringIO('\n'.join(lines)))]
        if not token:
            return names


def fetch(name: str) -> None:
    target = DATA / name
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ['kaggle', 'competitions', 'download', COMP, '-f', name, '-p', str(target.parent)],
        check=True,
        capture_output=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--all', action='store_true')
    group.add_argument('--task-ids', nargs='+')
    args = parser.parse_args()

    DATA.mkdir(exist_ok=True)
    if args.all:
        subprocess.run(['kaggle', 'competitions', 'download', COMP, '-p', str(DATA)], check=True)
        archive = DATA / f'{COMP}.zip'
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(DATA)
        archive.unlink()
        return

    names = list_files()
    shared = [n for n in names if n.startswith(SHARED)]
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(fetch, shared))

    tasks = {}
    with open(DATA / 'tasks.jsonl', encoding='utf-8') as f:
        for line in f:
            task = json.loads(line)
            tasks[task['instance_id']] = task
    wanted = []
    for task_id in args.task_ids:
        commit = tasks[task_id]['base_commit']
        wanted += [n for n in names if n.startswith(f'snapshots/{task_id}.')]
        wanted += [n for n in names if n.startswith(('graphs/', 'embeddings/')) and commit in n]
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(fetch, wanted))
    print(f'Downloaded {len(shared)} shared and {len(wanted)} task files to {DATA}')


if __name__ == '__main__':
    main()
