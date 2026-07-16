#!/bin/bash
# Host-side runner for the SHC container.
# Usage: toolchain/shc/run.sh <host-workdir> <command...>
# Mounts the verified vendor toolchain read-only at /opt/shc and the given
# work directory read-write at /work, then runs the command as the container
# user (mapped to the invoking uid so build output isn't root-owned).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENDOR_DIR="$REPO_ROOT/toolchain/vendor/shc"
WORKDIR="$(cd "$1" && pwd)"
shift

if [ ! -f "$VENDOR_DIR/shc.exe" ]; then
    echo "error: SHC toolchain not fetched — run toolchain/fetch-shc.sh (or make setup)" >&2
    exit 1
fi

exec docker run --rm \
    --user "$(id -u):$(id -g)" \
    --tmpfs "/whome:rw,exec,uid=$(id -u),gid=$(id -g)" \
    -v "$VENDOR_DIR":/opt/shc:ro \
    -v "$REPO_ROOT/toolchain/shc/compile.sh":/usr/local/bin/shc-compile:ro \
    -v "$WORKDIR":/work \
    atolm-shc -c "$*"
