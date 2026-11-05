# Source this inside a Slurm job to give the harness a Docker-compatible socket.
# Container storage goes in node-local /tmp, because network filesystems usually
# don't work for it. Each job gets its own storage and cleans it up on exit.
: "${SLURM_JOB_ID:?Run this inside a Slurm job}"

PODMAN_DIR="/tmp/$USER/podman-$SLURM_JOB_ID"
mkdir -p "$PODMAN_DIR/xdg"
chmod 700 "$PODMAN_DIR/xdg"
# sbatch copies the submitting shell's value, which may not exist inside this job.
export XDG_RUNTIME_DIR="$PODMAN_DIR/xdg"
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

if [[ ! -f data/sandbox_image.tar ]]; then
  echo "Missing data/sandbox_image.tar. Build it on a laptop and copy it here. See README.md." >&2
  exit 1
fi
podman load -q -i data/sandbox_image.tar
