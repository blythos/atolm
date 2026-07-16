#!/bin/bash
# Fetch and verify the Hitachi SHC 5.0 (Release31) toolchain into
# toolchain/vendor/shc/ (gitignored). The compiler is proprietary: it is
# never committed, only fetched to the user's machine and hash-verified.
#
# Source: archive.org item "sega-saturn-sdks" (SDKs/Official/Hitachi/ inside
# the zip). If you already have the archive locally, skip the 229MB download:
#   SHC_ARCHIVE=/path/to/sega-saturn-sdks.zip toolchain/fetch-shc.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR_DIR="$REPO_ROOT/toolchain/vendor/shc"

# Pinned provenance (recorded in Bucket 0; see docs/ATTRIBUTION_AND_FINDINGS.md)
ARCHIVE_URL="${SHC_ARCHIVE_URL:-https://archive.org/download/sega-saturn-sdks/Sega%20Saturn%20SDKs.zip}"
ARCHIVE_SHA256="6631054c29e47e1565a6555b3d448a066cf64ea9c53835771e12d01f167e4353"
SHC_EXE_SHA256="7113feff1bd1f34915a52553848d9df545d1792d1972977d56a2a8536a2d94ab"
ARCHIVE_SUBDIR="SDKs/Official/Hitachi"

if [ -f "$VENDOR_DIR/shc.exe" ] && \
   echo "$SHC_EXE_SHA256  $VENDOR_DIR/shc.exe" | sha256sum -c - >/dev/null 2>&1; then
    echo "SHC toolchain already present and verified: $VENDOR_DIR"
    exit 0
fi

CACHE_DIR="$REPO_ROOT/toolchain/vendor/cache"
mkdir -p "$CACHE_DIR" "$VENDOR_DIR"

if [ -n "${SHC_ARCHIVE:-}" ]; then
    ARCHIVE="$SHC_ARCHIVE"
    echo "Using local archive: $ARCHIVE"
else
    ARCHIVE="$CACHE_DIR/sega-saturn-sdks.zip"
    if [ ! -f "$ARCHIVE" ]; then
        echo "Downloading $ARCHIVE_URL (~229MB)..."
        wget -q --show-progress -O "$ARCHIVE" "$ARCHIVE_URL"
    fi
fi

echo "Verifying archive sha256..."
echo "$ARCHIVE_SHA256  $ARCHIVE" | sha256sum -c -

echo "Extracting $ARCHIVE_SUBDIR/ ..."
python3 - "$ARCHIVE" "$ARCHIVE_SUBDIR" "$VENDOR_DIR" <<'EOF'
import os, sys, zipfile
archive, subdir, dest = sys.argv[1], sys.argv[2], sys.argv[3]
prefix = subdir.rstrip("/") + "/"
with zipfile.ZipFile(archive) as z:
    names = [n for n in z.namelist() if n.startswith(prefix) and not n.endswith("/")]
    if not names:
        sys.exit(f"error: no entries under {prefix} in {archive}")
    for n in names:
        out = os.path.join(dest, os.path.basename(n))
        with z.open(n) as src, open(out, "wb") as dst:
            dst.write(src.read())
    print(f"extracted {len(names)} files")
EOF

echo "Verifying shc.exe sha256..."
echo "$SHC_EXE_SHA256  $VENDOR_DIR/shc.exe" | sha256sum -c -

echo "SHC toolchain ready: $VENDOR_DIR"
