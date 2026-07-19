#!/bin/bash
# Instruction-level diff of two raw SH2 .text blobs (original vs recompile),
# rendered by asm-differ (simonlindholm/asm-differ, sh2 arch — the same
# differ sotn-decomp proved on Saturn). Adaptation notes: our compiler emits
# SYSROF and our binutils live in the atolm-shc container, so this wrapper
# (a) converts both blobs to minimal big-endian SH ELFs in the container,
# (b) points asm-differ at a container-delegating objdump, and
# (c) if a SYSROF .obj is given, annotates which differing offsets are
#     relocation holes (link-time values, not codegen differences).
#
# Usage: tools/fndiff.sh <workdir> <orig.bin> <new.bin> [unit.obj]
#   paths relative to <workdir>. asm-differ is fetched (pinned) into
#   tools-local/asm-differ on first use.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ASMDIFFER="$REPO_ROOT/tools-local/asm-differ"
ASMDIFFER_PIN=5f0f27e97b3d0433039e832ba537e2bfe70e4cb5

WORKDIR="$(cd "$1" && pwd)"; ORIG="$2"; NEW="$3"; OBJ="${4:-}"

if [ ! -d "$ASMDIFFER" ]; then
    git clone https://github.com/simonlindholm/asm-differ "$ASMDIFFER"
fi
git -C "$ASMDIFFER" checkout -q "$ASMDIFFER_PIN" 2>/dev/null || true

# raw -> ELF (big-endian SH), section .text, so objdump needs no -b binary
for f in "$ORIG:orig" "$NEW:new"; do
    bin="${f%%:*}"; base="${f##*:}"
    "$REPO_ROOT/tools/sh-elf.sh" "$WORKDIR" objcopy \
        -I binary -O elf32-sh -B sh --rename-section .data=.text \
        "$bin" "$base.elf"
done

# container-delegating objdump for asm-differ
cat > "$WORKDIR/objdump-bridge.sh" <<EOF
#!/bin/bash
exec "$REPO_ROOT/tools/sh-elf.sh" "$WORKDIR" objdump "\$@"
EOF
chmod +x "$WORKDIR/objdump-bridge.sh"

ORIG_SIZE=$(stat -c%s "$WORKDIR/$ORIG")
cat > "$WORKDIR/diff_settings.py" <<EOF
def apply(config, args):
    config["arch"] = "sh2"
    config["baseimg"] = "orig.elf"
    config["myimg"] = "new.elf"
    config["objdump_executable"] = "./objdump-bridge.sh"
    config["mapfile"] = None
EOF

# reloc-hole annotation from the SYSROF object, if provided
if [ -n "$OBJ" ]; then
    echo "== relocation holes in $OBJ (link-time values; differences at"
    echo "== these offsets are NOT codegen differences):"
    python3 "$REPO_ROOT/tools/sysrof.py" --holes "$WORKDIR/$OBJ" || true
    echo
fi

# objcopy names the blob's symbols after the input file; disassemble the
# whole new .text via the start symbol
NEWSYM="_binary_$(echo "$NEW" | tr './-' '___')_start"

cd "$WORKDIR"
# shims: colorama/watchdog stand-ins (no pip on host); difflib algorithm
# avoids the optional levenshtein module. --format plain keeps output
# terminal- and log-friendly.
export PYTHONPATH="$REPO_ROOT/tools/asm-differ-shims${PYTHONPATH:+:$PYTHONPATH}"
exec python3 "$ASMDIFFER/diff.py" -e "$NEWSYM" 0 "$ORIG_SIZE" \
    --format plain --no-pager --algorithm difflib
