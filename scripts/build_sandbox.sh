#!/usr/bin/env bash
# Build the sandbox image and save it to data/sandbox_image.tar. Run this where Docker
# is available and copy the file to PACE, because building with Podman fails there.
# Needs the shared files in data/.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v docker >/dev/null; then
  echo "Docker isn't available. Build on a laptop, then copy data/sandbox_image.tar here." >&2
  exit 1
fi

[[ -d data/docker/wheels ]] || cp -R data/wheels data/docker/wheels
docker buildx build --platform linux/amd64 --load \
  -f docker/Dockerfile -t swebench-sandbox:latest data/docker
docker save swebench-sandbox:latest -o data/sandbox_image.tar
echo "Saved data/sandbox_image.tar"
