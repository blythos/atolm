#!/bin/bash
# Host-side bridge to the container's sh-elf binutils (they are not
# installed on the host — charter environment rule).
# Usage: tools/sh-elf.sh <workdir> <tool> [args...]
#   e.g. tools/sh-elf.sh build/try/0x600abcd objdump -d -m sh2 -EB unit.elf
# The workdir is mounted at /work (container cwd); file arguments must be
# relative paths inside it.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKDIR="$1"; TOOL="$2"; shift 2
exec "$REPO_ROOT/toolchain/shc/run.sh" "$WORKDIR" "sh-elf-$TOOL $*"
