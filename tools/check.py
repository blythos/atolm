#!/usr/bin/env python3
"""make check: byte-identity of build/<TARGET> vs extracted/<TARGET>,
plus per-target match statistics. GREEN only on byte-identity.
"""
import os
import sys

from prg import REPO, load_manifests, sha256


def main():
    failures = 0
    for m in load_manifests():
        if m.get("role") != "build":
            continue
        target = m["target"]
        built = os.path.join(REPO, "build", target)
        extracted = os.path.join(REPO, "extracted", target)
        if not os.path.exists(built):
            print(f"check: FAIL {target}: build/{target} missing — run `make`")
            failures += 1
            continue
        with open(built, "rb") as f:
            b = f.read()
        with open(extracted, "rb") as f:
            e = f.read()

        units = m.get("units") or {}
        code = sum(s["end"] - s["start"] for s in m["segments"]
                   if s["type"] == "code")
        matched = sum(s["end"] - s["start"] for s in m["segments"]
                      if s["type"] == "code"
                      and units[s["unit"]]["status"] == "matched")

        if b == e:
            print(f"check: PASS {target}: byte-identical "
                  f"({len(b)} bytes, sha256 {sha256(b)[:16]}…); "
                  f"matched code {matched}/{code} bytes "
                  f"({100*matched/code if code else 0:.1f}%)")
        else:
            diff = sum(1 for x, y in zip(b, e) if x != y) + abs(len(b) - len(e))
            print(f"check: FAIL {target}: differs from original "
                  f"({diff} differing/extra bytes)")
            failures += 1
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
