#!/bin/bash
# Regenerate the local Ghidra project for a PRG target from a clean checkout
# + locally extracted content (Bucket 2 deliverable).
#
# The generated project is DISC-DERIVED and lives in gitignored tools-local/
# — it is never committed. This script, the seed detector (tools/sh2_map.py),
# the post-script (tools/ghidra_scripts/SeedAndExport.java) and the symbols
# file (config/symbols/) are the committed artifacts.
#
# Function boundaries are SEEDED from our prologue-based detector, not
# Ghidra's defaults (FINDINGS gotchas: multiple-return mis-splits, literal
# pools decoded as fake instructions).
#
# Usage: tools/ghidra_gen.sh [TARGET]        (default 1ST_READ.PRG)
# Env:   GHIDRA_HOME, JAVA_HOME override the tools-local/ defaults.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${1:-1ST_READ.PRG}"
GHIDRA_HOME="${GHIDRA_HOME:-$REPO/tools-local/ghidra_12.1.2_PUBLIC}"
if [ -z "${JAVA_HOME:-}" ]; then
    JAVA_HOME="$(echo "$REPO"/tools-local/jdk-21*)"
fi
export JAVA_HOME

[ -d "$GHIDRA_HOME" ] || {
    echo "ghidra_gen: Ghidra not found at $GHIDRA_HOME" >&2
    echo "  install: download ghidra_12.1.2_PUBLIC zip into tools-local/" >&2
    exit 1
}
EXTRACTED="$REPO/extracted/$TARGET"
[ -f "$EXTRACTED" ] || {
    echo "ghidra_gen: extracted/$TARGET missing — run make extract" >&2
    exit 1
}

VMA_BASE="$(python3 -c "
import sys; sys.path.insert(0, '$REPO/tools')
from prg import load_manifests
print(hex(next(m for m in load_manifests()
               if m['target'] == '$TARGET')['vma_base']))")"

# 1. seeds from our detector
python3 "$REPO/tools/sh2_map.py" "$TARGET"
python3 -c "
import json
m = json.load(open('$REPO/build/analysis/$TARGET.map.json'))
with open('$REPO/build/analysis/$TARGET.seeds.txt', 'w') as f:
    f.write('\n'.join(hex(fn['vma']) for fn in m['functions']))
print('ghidra_gen: %d seeds' % len(m['functions']))"

# 2. clean project regeneration (never incremental — reproducibility is
#    the point)
PROJDIR="$REPO/tools-local/ghidra-projects/$TARGET"
rm -rf "$PROJDIR"
mkdir -p "$PROJDIR"

"$GHIDRA_HOME/support/analyzeHeadless" "$PROJDIR" atolm \
    -import "$EXTRACTED" \
    -processor "SuperH:BE:32:SH-2" \
    -loader BinaryLoader \
    -loader-baseAddr "$VMA_BASE" \
    -noanalysis \
    -scriptPath "$REPO/tools/ghidra_scripts" \
    -postScript SeedAndExport.java \
        "$REPO/build/analysis/$TARGET.seeds.txt" \
        "$REPO/build/analysis/$TARGET.ghidra.json" \
        "$REPO/config/symbols/$TARGET.sym"

echo "ghidra_gen: OK — project: tools-local/ghidra-projects/$TARGET"
echo "ghidra_gen: export: build/analysis/$TARGET.ghidra.json"
