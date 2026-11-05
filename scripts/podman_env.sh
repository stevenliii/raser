# Source this inside a Slurm job to give the harness a Docker-compatible socket.
# Container storage goes in node-local /tmp, because network filesystems usually
# don't work for it. Each job gets its own storage and cleans it up on exit.
: "${SLURM_JOB_ID:?Run this inside a Slurm job}"

PODMAN_DIR="/tmp/$USER/podman-$SLURM_JOB_ID"
mkdir -p "$PODMAN_DIR"
cat > "$PODMAN_DIR/storage.conf" <<CONF
[storage]
driver = "overlay"
graphroot = "$PODMAN_DIR/root"
runroot = "$PODMAN_DIR/run"

[storage.options.overlay]
ignore_chown_errors = "true"
CONF
export CONTAINERS_STORAGE_CONF="$PODMAN_DIR/storage.conf"
export DOCKER_HOST="unix://$PODMAN_DIR/podman.sock"

podman_cleanup() {
  [[ -n "${PODMAN_SERVICE_PID:-}" ]] && kill "$PODMAN_SERVICE_PID" 2>/dev/null
  podman unshare rm -rf "$PODMAN_DIR" 2>/dev/null || rm -rf "$PODMAN_DIR"
}
trap podman_cleanup EXIT

podman system service --time=0 "$DOCKER_HOST" 2>"$PODMAN_DIR/service.log" &
PODMAN_SERVICE_PID=$!
for _ in {1..30}; do
  [[ "$(curl -s --unix-socket "$PODMAN_DIR/podman.sock" http://d/_ping)" == "OK" ]] && break
  sleep 1
done
if [[ "$(curl -s --unix-socket "$PODMAN_DIR/podman.sock" http://d/_ping)" != "OK" ]]; then
  echo "Podman socket did not start:" >&2
  cat "$PODMAN_DIR/service.log" >&2
  exit 1
fi

# Load the saved sandbox image, or build it if this is the first job.
if [[ -f data/sandbox_image.tar ]]; then
  podman load -q -i data/sandbox_image.tar
else
  scripts/build_sandbox.sh
fi
