#!/usr/bin/env python3
"""make all: assemble build/<TARGET> for every `role: build` manifest.

Code segments come from compiled units — each hash-verified against its
manifest record before splicing, so a unit that stops matching can never
silently ship inside a "green" PRG. Unmatched/data segments are spliced
from the locally-extracted original (placeholder mechanism).
"""
import os
import sys

from prg import REPO, load_manifests, compile_unit, sha256


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
    if segments[0]["start"] != 0 or segments[-1]["end"] != m["size"]:
        fail(f"{target}: segment map must cover [0, size)")
    for a, b in zip(segments, segments[1:]):
        if a["end"] != b["start"]:
            fail(f"{target}: segment map gap/overlap at {a['end']:#x}")

    units = m.get("units") or {}
    out = bytearray()
    matched_bytes = code_bytes = 0
    for seg in segments:
        start, end, typ = seg["start"], seg["end"], seg["type"]
        length = end - start
        if typ == "code":
            code_bytes += length
            unit = units[seg["unit"]]
            if unit["status"] == "matched":
                workdir = os.path.join(REPO, "build/obj", target, seg["unit"])
                data = compile_unit(seg["unit"], unit, workdir)
                if len(data) != length or sha256(data) != unit["sha256"]:
                    fail(f"{target}: unit {seg['unit']} no longer matches its "
                         f"manifest proof (got {len(data)} bytes, "
                         f"sha256 {sha256(data)[:16]}…)")
                out += data
                matched_bytes += length
            else:
                # placeholder: not yet matched, splice original bytes
                out += orig[start:end]
        elif typ in ("data", "code_unmatched"):
            out += orig[start:end]
        else:
            fail(f"{target}: unknown segment type {typ!r}")

    dest = os.path.join(REPO, "build", target)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(out)
    print(f"build: {target}: wrote build/{target} "
          f"({len(out)} bytes; matched code {matched_bytes}/{code_bytes} bytes)")


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
