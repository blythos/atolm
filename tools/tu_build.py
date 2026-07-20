#!/usr/bin/env python3
"""Translation-unit reconstruction driver (Bucket 4 STOP 2).

Given a unit seed (or explicit member VMAs), close the translation unit
(tools/tu_cluster.py), co-compile a reconstructed source over the whole unit
span in the SHC container, and byte-diff PER MEMBER — so a unit that is not
whole-unit-identical still reports which functions matched and classifies each
residual. This is the scale-out unit of work: match clusters, not functions.

Per-member verdict uses the original member code extents (reachability) as
boundaries; the recompiled unit is sliced at the same cumulative offsets
(functions emit in source order, so member k starts at sum of sizes 0..k-1).
A member is BYTE-IDENTICAL when its slice equals the original's.

Usage:
  python3 tools/tu_build.py <seed_vma> --src FILE [--flags "..."]
  python3 tools/tu_build.py --members 0x.. ,0x.. --src FILE
Prints per-member diff + a whole-unit verdict; exit 0 iff whole unit identical.
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prg import REPO
import tu_cluster

VMA_BASE = 0x06006000
CANON_FLAGS = "-optimize=1 -speed -macsave=0"


def member_sizes(members, insn):
    """Original code size of each member = reachability extent - start."""
    return [tu_cluster.flow_extent(m, insn) - m for m in members]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seed", nargs="?")
    ap.add_argument("--members")
    ap.add_argument("--src", required=True)
    ap.add_argument("--flags", default=CANON_FLAGS)
    ap.add_argument("--size", type=int, help="override unit span in bytes")
    args = ap.parse_args()

    insn, starts, poolw, endfile = tu_cluster.load()
    rel = tu_cluster.build_relations(insn, starts, poolw, endfile)
    if args.members:
        members = sorted(int(x, 16) for x in args.members.split(","))
        unit_start = members[0]
        unit_end = max(tu_cluster.flow_extent(m, insn) for m in members)
    else:
        members, unit_start, unit_end = tu_cluster.minimal_unit(
            int(args.seed, 16), insn, starts, endfile)
    size = args.size if args.size else unit_end - unit_start
    sizes = member_sizes(members, insn)

    trydir = os.path.join(REPO, "build/try", f"unit_0x{unit_start:07x}")
    os.makedirs(trydir, exist_ok=True)
    prg = os.path.join(REPO, "extracted/1ST_READ.PRG")
    off = unit_start - VMA_BASE
    orig = open(prg, "rb").read()[off:off + size]
    open(os.path.join(trydir, "orig.bin"), "wb").write(orig)

    import shutil
    shutil.copy(os.path.join(REPO, args.src), os.path.join(trydir, "UNIT.C"))
    r = subprocess.run(
        [os.path.join(REPO, "toolchain/shc/run.sh"), trydir,
         f"shc-compile UNIT.C unit {args.flags}"],
        capture_output=True, text=True)
    binp = os.path.join(trydir, "unit.bin")
    if not os.path.exists(binp):
        print("COMPILE ERROR:\n", (r.stdout + r.stderr)[-1200:])
        sys.exit(2)
    new = open(binp, "rb").read()

    print(f"unit 0x{unit_start:07x}: {len(members)} members, "
          f"span {size} B  (orig {len(orig)} B, recompiled {len(new)} B)")
    print(f"# member          size  differing  verdict")
    cur = 0
    all_ok = len(orig) == len(new)
    for m, sz in zip(members, sizes):
        o = orig[cur:cur + sz]
        n = new[cur:cur + sz]
        d = abs(len(o) - len(n)) + sum(a != b for a, b in zip(o, n))
        verdict = "BYTE-IDENTICAL" if (d == 0 and len(o) == len(n)) else "drift"
        if d:
            all_ok = False
        print(f"  0x{m:07x}   {sz:5}   {d:6}    {verdict}")
        cur += sz
    tail = len(orig) - cur
    if tail > 0:
        d = sum(a != b for a, b in zip(orig[cur:], new[cur:cur + tail]))
        print(f"  (trailing {tail} B: {d} differing)")
    print(f"whole-unit: {'MATCH' if all_ok else 'NON-MATCH'} "
          f"({sum(a!=b for a,b in zip(orig,new))+abs(len(orig)-len(new))} "
          f"bytes differ)")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
