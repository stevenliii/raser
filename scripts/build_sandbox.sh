#!/usr/bin/env bash
# Build the sandbox image. Needs Docker and the shared files in data/.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -d data/docker/wheels ]] || cp -R data/wheels data/docker/wheels
docker buildx build --platform linux/amd64 --load \
  -f data/docker/Dockerfile.public -t swebench-sandbox:base data/docker
docker buildx build --platform linux/amd64 --load \
  -f docker/Dockerfile -t swebench-sandbox:latest docker
