#!/usr/bin/env python
"""Build one package set per task, using versions available when the task was created.

Each task's dependencies come from its own snapshot, resolved with `uv --exclude-newer`
at the task's date. If that fails, usually because an old version has no build for the
sandbox's Python, the build relaxes exact pins and then the date. manifest.json records
which attempt each task used.

Writes envs/<instance_id>.tar for run_eval.py --task-envs. Needs internet, but sandboxes
stay offline because the archives are built in advance.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OWN_PACKAGE = {
    'fastapi/fastapi': 'fastapi',
    'Textualize/rich': 'rich',
    'psf/requests': 'requests',
    'encode/httpx': 'httpx',
}
# Runtime dependencies that these repos declare in setup.py rather than a readable file.
EXTRA_REQUIREMENTS = {
    'psf/requests': ['urllib3', 'certifi', 'idna', 'charset-normalizer', 'PySocks'],
    'encode/httpx': ['h11', 'httpcore', 'anyio', 'sniffio', 'idna'],
}
# Development tools the tests don't import. The sandbox image provides pytest.
SKIP = {
    'pytest', 'pytest-cov', 'coverage', 'mypy', 'ruff', 'black', 'isort', 'flake8',
    'pre-commit', 'asv', 'build', 'twine', 'wheel', 'unasync', 'importlib-metadata',
    'mkdocs', 'markdown', 'click', 'jinja2-cli',
}
NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*')


def normalize(name: str) -> str:
    return re.sub(r'[-_.]+', '-', name).lower()


def requirement_name(requirement: str) -> str:
    match = NAME.match(requirement.strip())
    return normalize(match.group(0)) if match else ''


def poetry_version(spec: str) -> str:
    """Convert Poetry's ^ and ~ constraints to standard ones."""
    spec = spec.strip()
    if spec == '*':
        return ''
    match = re.fullmatch(r'([\^~])(\d+)(?:\.(\d+))?(?:\.(\d+))?', spec)
    if not match:
        return spec
    kind, major, minor, _ = match.groups()
    if kind == '^' and int(major) > 0:
        upper = f'{int(major) + 1}'
    else:
        upper = f'{major}.{int(minor or 0) + 1}'
    return f'>={spec[1:]},<{upper}'


def read_requirements_file(tar: tarfile.TarFile, name: str, seen: set[str]) -> list[str]:
    if name in seen:
        return []
    seen.add(name)
    try:
        member = tar.extractfile(f'./{name}')
    except KeyError:
        return []
    if member is None:
        return []
    requirements = []
    for line in member.read().decode(errors='ignore').splitlines():
        line = line.split(' #')[0].strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith(('-r ', '--requirement ')):
            requirements += read_requirements_file(tar, line.split(maxsplit=1)[1], seen)
        elif not line.startswith('-'):
            requirements.append(line)
    return requirements


def collect_requirements(snapshot: Path, repo: str) -> list[str]:
    requirements = list(EXTRA_REQUIREMENTS.get(repo, []))
    with tarfile.open(snapshot) as tar:
        names = set(tar.getnames())
        if './pyproject.toml' in names:
            data = tomllib.loads(tar.extractfile('./pyproject.toml').read().decode())
            project = data.get('project', {})
            requirements += project.get('dependencies', [])
            requirements += project.get('optional-dependencies', {}).get('all', [])
            for group in ('tests', 'test', 'dev'):
                entries = data.get('dependency-groups', {}).get(group, [])
                requirements += [entry for entry in entries if isinstance(entry, str)]
            poetry = data.get('tool', {}).get('poetry', {})
            sections = [poetry.get('dependencies', {}), poetry.get('dev-dependencies', {})]
            sections.append(poetry.get('group', {}).get('dev', {}).get('dependencies', {}))
            for section in sections:
                for name, spec in section.items():
                    if isinstance(spec, dict):
                        if spec.get('optional') or 'python' in spec:
                            continue
                        spec = spec.get('version', '*')
                    requirements.append(f'{name}{poetry_version(spec)}')
        for name in ('requirements-tests.txt', 'requirements-dev.txt', 'requirements.txt'):
            if f'./{name}' in names:
                requirements += read_requirements_file(tar, name, set())
                break

    excluded = SKIP | {'python', OWN_PACKAGE.get(repo, '')}
    kept = {}
    for requirement in requirements:
        name = requirement_name(requirement)
        if name and name not in excluded:
            kept[requirement] = None
    return list(kept)


def uv_install(requirements_file: Path, target: Path, cutoff: str | None, python: str) -> str | None:
    """Install into target and return the error text, or None on success."""
    shutil.rmtree(target, ignore_errors=True)
    command = [
        'uv', 'pip', 'install', '--target', str(target), '--python-version', python,
        '--python-platform', 'x86_64-manylinux_2_28', '--only-binary', ':all:',
        '--no-config', '-q', '-r', str(requirements_file),
    ]
    if cutoff:
        command += ['--exclude-newer', cutoff]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return None if result.returncode == 0 else (result.stderr or result.stdout)[-1500:]


def build(task: dict, data_dir: Path, out_dir: Path, python: str) -> dict:
    instance_id, repo = task['instance_id'], task['repo']
    snapshot = data_dir / 'snapshots' / f'{instance_id}.tgz'
    entry = {'instance_id': instance_id, 'repo': repo, 'status': 'failed', 'cutoff': task['created_at']}
    if not snapshot.exists():
        entry['error'] = f'Missing {snapshot}'
        return entry
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        requirements = collect_requirements(snapshot, repo)
        entry['requirements'] = requirements
        requirements_file = tmp_path / 'requirements.txt'
        target = tmp_path / 'site'
        relaxed = [re.sub(r'==[^,;\s]+', '', requirement) for requirement in requirements]
        attempts = (
            ('date_cutoff', requirements, task['created_at']),
            ('date_cutoff_relaxed_pins', relaxed, task['created_at']),
            ('latest_relaxed_pins', relaxed, None),
        )
        for status, attempt, cutoff in attempts:
            requirements_file.write_text('\n'.join(attempt) + '\n', encoding='utf-8')
            error = uv_install(requirements_file, target, cutoff, python)
            if error is None:
                entry['status'] = status
                entry['cutoff'] = cutoff
                break
            entry[f'{status}_error'] = error
        else:
            entry['error'] = error
            return entry

        # A dependency can pull in the repo's own package, which must not hide the task's code.
        own = OWN_PACKAGE.get(repo)
        if own:
            for path in list(target.glob(f'{own}')) + list(target.glob(f'{own}-*.dist-info')):
                shutil.rmtree(path, ignore_errors=True)

        with tarfile.open(out_dir / f'{instance_id}.tar', 'w') as archive:
            for path in sorted(target.iterdir()):
                archive.add(path, arcname=path.name)
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    parser.add_argument('--out-dir', type=Path, default=ROOT / 'envs')
    parser.add_argument('--task-ids', nargs='+', help='Only these tasks; defaults to all')
    parser.add_argument('--python', default='3.13', help="The sandbox image's Python version")
    parser.add_argument('--workers', type=int, default=8)
    args = parser.parse_args()

    with open(args.data_dir / 'tasks.jsonl', encoding='utf-8') as f:
        tasks = [json.loads(line) for line in f]
    if args.task_ids:
        wanted = set(args.task_ids)
        tasks = [t for t in tasks if t['instance_id'] in wanted]
    args.out_dir.mkdir(parents=True, exist_ok=True)

    with ThreadPoolExecutor(args.workers) as pool:
        entries = list(pool.map(lambda t: build(t, args.data_dir, args.out_dir, args.python), tasks))

    manifest = args.out_dir / 'manifest.json'
    previous = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {}
    previous.update({entry['instance_id']: entry for entry in entries})
    manifest.write_text(json.dumps(previous, indent=2), encoding='utf-8')

    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry['status']] = counts.get(entry['status'], 0) + 1
    print(f'Built {len(entries)} tasks: {counts}')
    for entry in entries:
        if entry['status'] == 'failed':
            print(f'  FAILED {entry["instance_id"]}: {entry.get("error", "")[-300:]}')


if __name__ == '__main__':
    main()
