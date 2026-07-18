#!/usr/bin/env python3
"""Spot-check tool: the full evidence chain for any address in a mapped
target (Bucket 2 verification discipline — segmentation claims must be
checkable per address).

Usage: python3 tools/segment_report.py <addr> [TARGET]
  <addr>  vma (>= vma_base) or file offset, hex or decimal

Reads the committed manifest plus the regenerable local analysis artifacts
(build/analysis/*.json — rerun tools/sh2_map.py and tools/ghidra_gen.sh if
missing)."""
import bisect
import json
import os
import sys

from prg import REPO, load_manifests


def main():
    addr = int(sys.argv[1], 0)
    target = sys.argv[2] if len(sys.argv) > 2 else "1ST_READ.PRG"
    m = next(x for x in load_manifests() if x["target"] == target)
    base, size = m["vma_base"], m["size"]
    vma = addr if addr >= base else base + addr
    off = vma - base
    if not 0 <= off < size:
        sys.exit(f"address {addr:#x} outside {target}")
    print(f"{target} vma {vma:#x} (file offset {off:#x})")

    for seg in m.get("segments") or []:
        if seg["start"] <= off < seg["end"]:
            print(f"  segment [{seg['start']:#x},{seg['end']:#x}) "
                  f"state={seg['state']}"
                  + (f" unit={seg['unit']}" if "unit" in seg else ""))
            if "evidence" in seg:
                print(f"    evidence: {seg['evidence'].strip()}")

    adir = os.path.join(REPO, "build/analysis")
    mp = os.path.join(adir, f"{target}.map.json")
    if os.path.exists(mp):
        d = json.load(open(mp))
        fns = sorted(d["functions"], key=lambda f: f["vma"])
        vmas = [f["vma"] for f in fns]
        i = bisect.bisect_right(vmas, vma) - 1
        if i >= 0:
            f = fns[i]
            print(f"  detector: nearest start at/below: {f['vma']:#x} "
                  f"evidence={'+'.join(f['evidence'])}")
        pw = d["pool_widths"]
        for pa in (vma, vma - 2):
            if f"{pa:#x}" in pw:
                v = d["pool_values"].get(f"{pa:#x}")
                print(f"  detector: literal-pool slot at {pa:#x} "
                      f"width={pw[f'{pa:#x}']}"
                      + (f" value={v:#x}" if v else ""))
    else:
        print("  (run tools/sh2_map.py for detector evidence)")

    gp = os.path.join(adir, f"{target}.ghidra.json")
    if os.path.exists(gp):
        g = json.load(open(gp))
        for f in g["functions"]:
            if f["entry"] <= vma < f["entry"] + f["size"]:
                print(f"  ghidra: inside {f['name']} "
                      f"[{f['entry']:#x}, +{f['size']}) "
                      f"callers={f['callers']}")
                break
        cov = any(s <= vma < e for s, e in g["instr_ranges"])
        print(f"  ghidra: instruction-covered: {cov}")
    else:
        print("  (run tools/ghidra_gen.sh for Ghidra evidence)")

    mo = os.path.join(adir, f"{target}.modified.json")
    if os.path.exists(mo):
        mod = json.load(open(mo))["modified_regions"]
        hit = any(s <= off < e for s, e in mod)
        print(f"  runtime-modified in a Ymir savestate: {hit}")


if __name__ == "__main__":
    main()
