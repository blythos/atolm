#!/bin/bash
# Runs INSIDE the atolm-cygnus container.
# Usage: run_dosemu.sh <8.3-input-name> <8.3-output-name> <opt-level e.g. O1>
# Compiles a C file with the DOS-hosted Cygnus CC1.EXE via dosemu2.
# Gotcha (Bucket 0): dosemu's -K mounts the host dir; the drive letter varies
# by dosemu2 version — confirmed empirically, don't trust upstream comments.
set -e
IN="$1"
OUT="$2"
OPT="$3"

cd /work

cat > dosemurc <<EOF
\$_hdimage = '+0 /work +1'
EOF

test -d GCCSH || cp -r /opt/GCCSH/cygnus-2.7-96Q3-bin GCCSH

# Drive letters vary by dosemu2 version/config — probe empirically (BAT with
# `cd > WHERE.TXT`), don't guess. In this image (dosemu2 2.0pre9, this
# dosemurc): /work is the startup drive G:.
cat > BUILD.BAT <<EOF
@echo off
SET PATH=G:\GCCSH;%PATH%
CC1.EXE -$OPT -m2 -fsigned-char $IN -o $OUT
EOF

dosemu -quiet -dumb -f /work/dosemurc -K /work -E "BUILD.BAT"
