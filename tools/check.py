#!/usr/bin/env python3
"""make check: byte-identity of build/<TARGET> vs extracted/<TARGET>,
plus the full five-state split per target. GREEN only on byte-identity.
"""
import os
import sys

from prg import REPO, load_manifests, sha256, validate_manifest, format_split


def check_segment_hashes(m):
    """Any manifest with a segment map + a locally extracted original gets
    its per-segment sha256 rows verified (works for proofs-only targets
    too — this is what makes the committed map spot-checkable)."""
    target = m["target"]
    extracted = os.path.join(REPO, "extracted", target)
    if not (m.get("segments") and os.path.exists(extracted)):
        return 0
    with open(extracted, "rb") as f:
        data = f.read()
    bad = 0
    for seg in m["segments"]:
        if "sha256" not in seg:
            continue
        h = sha256(data[seg["start"]:seg["end"]])
        if h != seg["sha256"]:
            print(f"check: FAIL {target}: segment "
                  f"[{seg['start']:#x},{seg['end']:#x}) hash mismatch")
            bad += 1
    if not bad:
        n = sum(1 for s in m["segments"] if "sha256" in s)
        print(f"check: PASS {target}: {n} segment hashes verified")
    return bad


def main():
    failures = 0
    for m in load_manifests():
        failures += check_segment_hashes(m)
        if m.get("role") != "build":
            continue
        target = m["target"]
        built = os.path.join(REPO, "build", target)
        extracted = os.path.join(REPO, "extracted", target)
        if not os.path.exists(built):
            print(f"check: FAIL {target}: build/{target} missing — run `make`")
            failures += 1
            continue
        errs = validate_manifest(m)
        if errs:
            for e in errs:
                print(f"check: FAIL {e}")
            failures += 1
            continue
        with open(built, "rb") as f:
            b = f.read()
        with open(extracted, "rb") as f:
            e = f.read()

        if b == e:
            print(f"check: PASS {target}: byte-identical "
                  f"({len(b)} bytes, sha256 {sha256(b)[:16]}…); "
                  f"{format_split(m)}")
        else:
            diff = sum(1 for x, y in zip(b, e) if x != y) + abs(len(b) - len(e))
            print(f"check: FAIL {target}: differs from original "
                  f"({diff} differing/extra bytes)")
            failures += 1
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
