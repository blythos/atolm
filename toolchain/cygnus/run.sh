#!/bin/bash
# Host-side runner for the Cygnus container (secondary toolchain).
# Usage: toolchain/cygnus/run.sh <host-workdir> <command...>
# Same pattern as toolchain/shc/run.sh: work dir mounted at /work, command
# run as the invoking uid with a tmpfs home for dosemu.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORKDIR="$(cd "$1" && pwd)"
shift

exec docker run --rm \
    --user "$(id -u):$(id -g)" \
    --tmpfs "/whome:rw,exec,uid=$(id -u),gid=$(id -g)" \
    -v "$REPO_ROOT/toolchain/cygnus/run_dosemu.sh":/usr/local/bin/cygnus-compile:ro \
    -v "$WORKDIR":/work \
    atolm-cygnus -c "$*"
