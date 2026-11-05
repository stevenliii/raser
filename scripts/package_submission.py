#!/usr/bin/env python
"""Validate an agent folder and zip it for Kaggle, with agent.yaml at the archive root."""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

from adk_submission import validate_directory
from swegemma.config import (
    ALLOWED_SUBMISSION_EXTENSIONS,
    MAX_SUBMISSION_SIZE_BYTES,
    build_submission_limits,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent', type=Path, default=ROOT / 'agents/gemma_baseline')
    parser.add_argument('--out', type=Path, default=ROOT / 'submission.zip')
    args = parser.parse_args()

    limits, _ = build_submission_limits()
    validate_directory(args.agent, limits=limits)
    files = sorted(p for p in args.agent.rglob('*') if p.is_file() and p.name != '.DS_Store')
    for path in files:
        if path.is_symlink():
            raise SystemExit(f'Symlinks are not allowed: {path}')
        if path.suffix.lower() not in ALLOWED_SUBMISSION_EXTENSIONS:
            raise SystemExit(f'Disallowed file type: {path}')
    total = sum(p.stat().st_size for p in files)
    if total > MAX_SUBMISSION_SIZE_BYTES:
        raise SystemExit(f'Agent is too large: {total} bytes')

    with zipfile.ZipFile(args.out, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(args.agent))
    print(f'Wrote {args.out} with {len(files)} files, {total / 1024:.1f} KiB unpacked')


if __name__ == '__main__':
    main()
