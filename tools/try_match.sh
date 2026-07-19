#!/bin/bash
# One-command per-function match attempt (Bucket 3 workflow, docs/WORKFLOW.md):
#   extract original bytes -> compile the draft -> byte-diff -> report.
#
# Usage: tools/try_match.sh <vma> [options]
#   <vma>          function start, e.g. 0x0600abcd (config/targets/
#                  1ST_READ.functions.tsv addressing)
#   --src FILE     draft source (default src/1ST_READ/func_<vma>.c)
#   --size N       original byte span to match (default: distance to the
#                  next function start in the inventory — includes the
#                  literal pool, per the unit-owns-its-pools rule)
#   --flags "..."  compiler flags (default: -optimize=1 -speed)
#
# On MATCH: prints tool-generated proof values (sizes, sha256) ready for the
# manifest — never hand-copy hashes from anywhere else (charter §5).
# On NON-MATCH: prints differing-byte count, first divergence, relocation-
# hole annotation from the SYSROF object, and the asm-differ view.
# Exit code: 0 match, 1 non-match, 2 usage/build error.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TSV="$REPO_ROOT/config/targets/1ST_READ.functions.tsv"
PRG="$REPO_ROOT/extracted/1ST_READ.PRG"
VMA_BASE=$((0x06006000))

VMA=""; SRC=""; SIZE=""; FLAGS="-optimize=1 -speed"
while [ $# -gt 0 ]; do
    case "$1" in
        --src) SRC="$2"; shift 2;;
        --size) SIZE="$2"; shift 2;;
        --flags) FLAGS="$2"; shift 2;;
        -*) echo "unknown option $1" >&2; exit 2;;
        *) VMA="$1"; shift;;
    esac
done
[ -n "$VMA" ] || { grep '^#' "$0" | sed -n '2,20p'; exit 2; }
[ -f "$PRG" ] || { echo "error: extracted/1ST_READ.PRG missing (make extract)" >&2; exit 2; }

VMA_DEC=$((VMA))
ADDR_HEX=$(printf '%08x' "$VMA_DEC")
SRC="${SRC:-$REPO_ROOT/src/1ST_READ/func_${ADDR_HEX}.c}"
[ -f "$SRC" ] || { echo "error: no draft source at $SRC" >&2; exit 2; }

# default size: span to the next inventory function start
if [ -z "$SIZE" ]; then
    SIZE=$(awk -v vma="$VMA_DEC" 'BEGIN{FS="\t"} /^#/{next}
        { a=strtonum($1);
          if (a==vma) found=1;
          else if (found && a>vma) { print a-vma; exit } }' "$TSV")
    [ -n "$SIZE" ] || { echo "error: $VMA not in inventory (use --size)" >&2; exit 2; }
fi

TRYDIR="$REPO_ROOT/build/try/0x$ADDR_HEX"
mkdir -p "$TRYDIR"
OFFSET=$((VMA_DEC - VMA_BASE))

python3 - "$PRG" "$OFFSET" "$SIZE" "$TRYDIR/orig.bin" <<'EOF'
import sys
prg, off, size, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
data = open(prg, 'rb').read()[off:off+int(size)]
assert len(data) == int(size), "span exceeds file"
open(out, 'wb').write(data)
EOF

cp "$SRC" "$TRYDIR/UNIT.C"
if ! "$REPO_ROOT/toolchain/shc/run.sh" "$TRYDIR" \
        "shc-compile UNIT.C unit $FLAGS" > "$TRYDIR/compile.log" 2>&1; then
    echo "COMPILE ERROR — $TRYDIR/compile.log:" >&2
    tail -15 "$TRYDIR/compile.log" >&2
    exit 2
fi

ORIG_SHA=$(sha256sum "$TRYDIR/orig.bin" | cut -d' ' -f1)
NEW_SHA=$(sha256sum "$TRYDIR/unit.bin" | cut -d' ' -f1)
ORIG_SIZE=$(stat -c%s "$TRYDIR/orig.bin")
NEW_SIZE=$(stat -c%s "$TRYDIR/unit.bin")

echo "try_match 0x$ADDR_HEX: original $ORIG_SIZE B, recompiled $NEW_SIZE B"
if [ "$ORIG_SHA" = "$NEW_SHA" ]; then
    echo "MATCH — byte-identical (sha256 $ORIG_SHA)"
    echo
    echo "manifest record (tool-generated values):"
    echo "    source: ${SRC#$REPO_ROOT/}"
    echo "    size: $ORIG_SIZE"
    echo "    status: matched"
    echo "    compiler: shc-5.0-r31"
    echo "    flags: [$(echo "$FLAGS" | sed 's/ /, /g')]"
    echo "    sha256: $ORIG_SHA"
    echo "    matched: $(date +%F)"
    exit 0
fi

DIFFBYTES=$(python3 - "$TRYDIR/orig.bin" "$TRYDIR/unit.bin" <<'EOF'
import sys
a = open(sys.argv[1],'rb').read(); b = open(sys.argv[2],'rb').read()
n = sum(x != y for x, y in zip(a, b)) + abs(len(a) - len(b))
first = next((i for i,(x,y) in enumerate(zip(a,b)) if x!=y), min(len(a),len(b)))
print(f"{n} {first:#x}")
EOF
)
echo "NON-MATCH — ${DIFFBYTES% *} differing/extra bytes, first at offset ${DIFFBYTES#* }"
echo "asm-differ view (reloc holes annotated):"
"$REPO_ROOT/tools/fndiff.sh" "$TRYDIR" orig.bin unit.bin unit.obj || true
exit 1
