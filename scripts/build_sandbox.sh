#!/usr/bin/env bash
# Build the sandbox image with Docker if available, otherwise Podman.
# Needs the shared files in data/. Podman builds are saved so later jobs can load them.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -d data/docker/wheels ]] || cp -R data/wheels data/docker/wheels

if command -v docker >/dev/null; then
  docker buildx build --platform linux/amd64 --load \
    -f docker/Dockerfile -t swebench-sandbox:latest data/docker
else
  podman build --isolation chroot -f docker/Dockerfile -t swebench-sandbox:latest data/docker
  podman save -o data/sandbox_image.tar swebench-sandbox:latest
fi
