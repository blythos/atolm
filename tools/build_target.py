#!/usr/bin/env python3
"""make all: assemble build/<TARGET> for every `role: build` manifest.

`matched` segments come from compiled units — each hash-verified against
its manifest record before splicing, so a unit that stops matching can
never silently ship inside a "green" PRG. Every other state (attempted /
unattempted / library-candidate / data) is spliced from the
locally-extracted original (placeholder mechanism).
"""
import os
import sys

from prg import (REPO, load_manifests, compile_unit, sha256,
                 validate_manifest, format_split)


def fail(msg):
    print(f"build: FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def build_one(m):
    target = m["target"]
    extracted = os.path.join(REPO, "extracted", target)
    if not os.path.exists(extracted):
        fail(f"{target}: extracted/{target} missing — run `make extract`")
    with open(extracted, "rb") as f:
        orig = f.read()

    segments = m.get("segments") or []
    if not segments:
        fail(f"{target}: no segment map")
    errs = validate_manifest(m)
    if errs:
        fail(f"{target}: invalid manifest:\n  " + "\n  ".join(errs))

    units = m.get("units") or {}
    out = bytearray()
    for seg in segments:
        start, end, state = seg["start"], seg["end"], seg["state"]
        if state == "matched":
            unit = units[seg["unit"]]
            workdir = os.path.join(REPO, "build/obj", target, seg["unit"])
            data = compile_unit(seg["unit"], unit, workdir)
            if len(data) != end - start or sha256(data) != unit["sha256"]:
                fail(f"{target}: unit {seg['unit']} no longer matches its "
                     f"manifest proof (got {len(data)} bytes, "
                     f"sha256 {sha256(data)[:16]}…)")
            out += data
        else:
            # placeholder: everything not matched is spliced from the
            # locally-extracted original
            out += orig[start:end]

    dest = os.path.join(REPO, "build", target)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(out)
    print(f"build: {target}: wrote build/{target} ({len(out)} bytes; "
          f"{format_split(m)})")


def main():
    built = 0
    for m in load_manifests():
        if m.get("role") == "build":
            build_one(m)
            built += 1
    if not built:
        fail("no role: build targets")


if __name__ == "__main__":
    main()
