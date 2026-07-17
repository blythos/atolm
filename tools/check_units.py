#!/usr/bin/env python3
"""make check-functions: recompile every `status: matched` unit from
committed C and verify its sha256 proof. Needs no disc content — hash
equality with the manifest is the proof — so CI runs this.

With --compile-attempted, also compiles `status: attempted` units to prove
the committed C still builds; they are reported (byte count) but cannot
fail the hash check.
"""
import os
import sys

from prg import (REPO, load_manifests, compile_unit, verify_unit, sha256,
                 validate_manifest)


def main():
    compile_attempted = "--compile-attempted" in sys.argv[1:]
    manifests = load_manifests()
    invalid = [e for m in manifests for e in validate_manifest(m)]
    if invalid:
        for e in invalid:
            print(f"check-functions: FAIL {e}")
        sys.exit(1)
    total = failed = 0
    for m in manifests:
        for name, unit in (m.get("units") or {}).items():
            if unit["status"] == "attempted" and compile_attempted:
                workdir = os.path.join(REPO, "build/proof", m["target"], name)
                data = compile_unit(name, unit, workdir)
                print(f"check-functions: BUILT {m['target']}:{name} "
                      f"(attempted, {len(data)} bytes compiled)")
                continue
            if unit["status"] != "matched":
                continue
            total += 1
            workdir = os.path.join(REPO, "build/proof", m["target"], name)
            ok, data = verify_unit(name, unit, workdir)
            if ok:
                print(f"check-functions: PASS {m['target']}:{name} "
                      f"({unit['size']} bytes, sha256 {unit['sha256'][:16]}…)")
            else:
                print(f"check-functions: FAIL {m['target']}:{name} — got "
                      f"{len(data)} bytes, sha256 {sha256(data)[:16]}…, "
                      f"manifest says {unit['size']} / {unit['sha256'][:16]}…")
                failed += 1
    print(f"check-functions: {total - failed}/{total} matched units verified")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
