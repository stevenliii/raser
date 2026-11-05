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
import os
import subprocess
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

COMP = 'gemma-4-developer-agent'
DOWNLOAD_URL = f'https://www.kaggle.com/api/v1/competitions/data/download-all/{COMP}'
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
        for line in lines:
            if line.startswith('Next Page Token'):
                token = line.split('=', 1)[1].strip()
        # The CLI can print warnings before the CSV, so start at the header.
        header = next((i for i, line in enumerate(lines) if line.startswith('name,')), None)
        if header is None:
            raise SystemExit(f'Unexpected output from the Kaggle CLI:\n{out}')
        names += [row['name'] for row in csv.DictReader(io.StringIO('\n'.join(lines[header:])))]
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


def curl_auth_config() -> str:
    """Return curl config with Kaggle credentials, passed on stdin to keep them out of `ps`."""
    token = os.environ.get('KAGGLE_API_TOKEN')
    if token:
        return f'header = "Authorization: Bearer {token}"\n'
    for path in (Path.home() / '.kaggle/kaggle.json', Path.home() / '.config/kaggle/kaggle.json'):
        if path.exists():
            creds = json.loads(path.read_text(encoding='utf-8'))
            return f'user = "{creds["username"]}:{creds["key"]}"\n'
    raise SystemExit('No Kaggle credentials: set KAGGLE_API_TOKEN or add kaggle.json')


def download_all() -> None:
    # The Kaggle CLI ran out of memory on this archive, so stream it to disk with curl.
    archive = DATA / f'{COMP}.zip'
    subprocess.run(
        ['curl', '-L', '--fail', '-o', str(archive), '--config', '-', DOWNLOAD_URL],
        input=curl_auth_config(),
        text=True,
        check=True,
    )
    with zipfile.ZipFile(archive) as zf:
        corrupt = zf.testzip()
        if corrupt:
            raise SystemExit(f'Corrupt download at {corrupt}. Delete {archive} and try again.')
        zf.extractall(DATA)
    archive.unlink()
    print(f'Extracted the dataset to {DATA}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--all', action='store_true')
    group.add_argument('--task-ids', nargs='+')
    args = parser.parse_args()

    DATA.mkdir(exist_ok=True)
    if args.all:
        download_all()
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
