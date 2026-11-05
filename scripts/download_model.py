#!/usr/bin/env python
"""Download a competition Gemma 4 model into models/<name>. Run this on PACE, not a laptop."""
from __future__ import annotations

import argparse
import subprocess
import tarfile
from pathlib import Path

from download_data import curl_auth_config

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://www.kaggle.com/api/v1/models/google/gemma-4/other/{name}/{version}/download'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', default='gemma-4-12b-it-qat-w4a16-ct')
    parser.add_argument('--version', default='2')
    parser.add_argument('--out-dir', type=Path, default=ROOT / 'models')
    args = parser.parse_args()

    target = args.out_dir / args.name
    target.mkdir(parents=True, exist_ok=True)
    archive = args.out_dir / f'{args.name}.tar.gz'
    subprocess.run(
        ['curl', '-L', '--fail', '-o', str(archive), '--config', '-',
         URL.format(name=args.name, version=args.version)],
        input=curl_auth_config(),
        text=True,
        check=True,
    )
    with tarfile.open(archive) as tar:
        tar.extractall(target, filter='data')
    archive.unlink()
    if not (target / 'config.json').exists():
        raise SystemExit(f'No config.json in {target}. Check the download.')
    print(f'Model ready in {target}')


if __name__ == '__main__':
    main()
