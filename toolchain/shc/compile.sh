#!/bin/bash
# Runs INSIDE the atolm-shc container.
# Usage: compile.sh <SOURCE.C> <output-prefix> [compiler flags...]
#
# Produces <prefix>.obj (Hitachi SYSROF), <prefix>.elf, <prefix>.bin
# (raw .text bytes) in the current directory (/work).
#
# Notes carried over from Bucket 0 (see docs/ATTRIBUTION_AND_FINDINGS.md):
# - elfcnv.exe mislabels its ELF output as little-endian; the bytes are
#   correct big-endian SH2. Disassemble with `sh-elf-objdump -EB -m sh2`.
# - elfcnv.exe fails ("Unknown relocation type") on objects with unresolved
#   external calls; sources must be self-contained or fully linked.
set -euo pipefail

SRC="$1"
PREFIX="$2"
shift 2

wine /opt/shc/shc.exe "$SRC" -object="$PREFIX.obj" "$@"

# elfcnv.exe exits 1 even on success ("ELFCNV successful"); trust the output
# file, not the exit code.
rm -f "$PREFIX.elf"
wine /opt/shc/elfcnv.exe "$PREFIX.obj" "$PREFIX.elf" || true
test -f "$PREFIX.elf" || { echo "error: elfcnv produced no $PREFIX.elf" >&2; exit 1; }

sh-elf-objcopy -O binary --only-section=.text "$PREFIX.elf" "$PREFIX.bin"
