#!/bin/bash
# Tripwire (legal rules, CLAUDE.md): fail if any committed file could carry
# binary or Sega-derived content. Checks `git ls-files` (what is/would be
# committed), not the working tree, so local gitignored disc data does not
# false-positive.
set -euo pipefail
cd "$(dirname "$0")/.."

fail=0

# 1. Banned artifact extensions — never committed, whatever their content.
BANNED_RE='\.(bin|prg|obj|elf|o|iso|img|exe|com|zip|7z|rar|tar|gz|cue|ccd|mds|mdf|sub|wav)$'
while IFS= read -r f; do
    if echo "$f" | grep -qiE "$BANNED_RE"; then
        echo "TRIPWIRE: banned extension: $f"
        fail=1
    fi
done < <(git ls-files)

# 2. No binary content: committed files must contain no NUL bytes.
while IFS= read -r f; do
    [ -f "$f" ] || continue
    if grep -qP '\x00' "$f" 2>/dev/null; then
        echo "TRIPWIRE: NUL byte (binary content) in: $f"
        fail=1
    fi
done < <(git ls-files)

# 3. No committed file may hash to a known original-content hash from the
#    manifests (a file matching one would BE Sega-derived bytes).
KNOWN=$(grep -rhoP 'sha256:\s*\K[0-9a-f]{64}' config/ | sort -u)
while IFS= read -r f; do
    [ -f "$f" ] || continue
    h=$(sha256sum "$f" | cut -d' ' -f1)
    if echo "$KNOWN" | grep -q "$h"; then
        echo "TRIPWIRE: file hashes to a known original-content hash: $f"
        fail=1
    fi
done < <(git ls-files)

if [ "$fail" -ne 0 ]; then
    echo "TRIPWIRE: FAIL"
    exit 1
fi
echo "TRIPWIRE: PASS ($(git ls-files | wc -l) committed files clean)"
