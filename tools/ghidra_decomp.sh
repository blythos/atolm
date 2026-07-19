#!/bin/bash
# Batch-decompile a list of addresses from the existing local Ghidra project
# (tools/ghidra_gen.sh must have run once). Drafts land in gitignored
# build/analysis/decomp/<TARGET>/ — consulted, never committed.
#
# Usage: tools/ghidra_decomp.sh <addrs.txt> [TARGET]
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
ADDRS="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
TARGET="${2:-1ST_READ.PRG}"
GHIDRA_HOME="${GHIDRA_HOME:-$REPO/tools-local/ghidra_12.1.2_PUBLIC}"
if [ -z "${JAVA_HOME:-}" ]; then
    JAVA_HOME="$(echo "$REPO"/tools-local/jdk-21*)"
fi
export JAVA_HOME

PROJDIR="$REPO/tools-local/ghidra-projects/$TARGET"
[ -d "$PROJDIR" ] || { echo "no project — run tools/ghidra_gen.sh first" >&2; exit 1; }
OUT="$REPO/build/analysis/decomp/$TARGET"
mkdir -p "$OUT"

"$GHIDRA_HOME/support/analyzeHeadless" "$PROJDIR" atolm \
    -process "$TARGET" -noanalysis \
    -scriptPath "$REPO/tools/ghidra_scripts" \
    -postScript DecompileList.java "$ADDRS" "$OUT"

echo "ghidra_decomp: drafts in build/analysis/decomp/$TARGET/"
