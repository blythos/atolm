#!/usr/bin/env python3
"""Distill the committed function-inventory snapshot from the detector map.

Reads build/analysis/<target>.map.json (the reachability-merged seed map from
sh2_map.py) and the disassembly, and emits the committed inventory TSV:

    vma\tsize\tcallers\tevidence

- size    : owned span — reachability code extent (flow_extent), capped at
            the next start (a function never owns bytes past its neighbour;
            trailing literal pools before the neighbour are excluded). Our own
            deterministic measure, replacing the Bucket-2 Ghidra body size
            which carried the braf-flap nondeterminism; stable across runs.
- callers : in-degree over intra-file call edges (bsr + jsr @Rn resolved from
            a nearby pool load), computed exactly as tools/callgraph.py does.
- evidence: the detector's evidence chain, '+'-joined (entry|prologue|bsr|
            jsr-pool|jmp-pool|ptr32).

No Sega bytes: addresses, sizes and evidence only. Fully reproducible from
committed tools + the (gitignored, disc-derived) map/disasm.

Usage: python3 tools/inventory_tsv.py [1ST_READ.PRG] > \
           config/targets/1ST_READ.functions.tsv
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prg import REPO
from sh2_map import flow_extent

POOL_LD = re.compile(r"mov\.l\s+0x[0-9a-f]+,r(\d+)\s*!\s*([0-9a-f]+)")
LINE = re.compile(r"^\s*([0-9a-f]+):\s+[0-9a-f]{2} [0-9a-f]{2}\s+(\S+)\s*(.*)")
EV_ORDER = ["entry", "prologue", "bsr", "jsr-pool", "jmp-pool", "ptr32"]


def load_insns(target):
    path = os.path.join(REPO, "build/analysis", f"{target}.disasm.txt")
    insns = {}
    with open(path) as f:
        for line in f:
            m = LINE.match(line)
            if m:
                insns[int(m.group(1), 16)] = (m.group(2), m.group(3))
    return insns


def caller_counts(starts, insn_map):
    """In-degree of each start over bsr + pool-resolved jsr edges, restricted
    to the caller's flow extent (matches tools/callgraph.py exactly)."""
    startset = set(starts)
    indeg = {s: 0 for s in starts}
    for s in starts:
        code_end = flow_extent(s, insn_map)
        loads, seen_edges = {}, set()
        pc = s
        while pc < code_end:
            if pc not in insn_map:
                pc += 2
                continue
            mnem, ops = insn_map[pc]
            pm = POOL_LD.search(f"{mnem} {ops}")
            if pm:
                loads[pm.group(1)] = int(pm.group(2), 16)
            tgt = None
            if mnem == "bsr":
                m = re.match(r"(0x[0-9a-f]+)", ops)
                if m:
                    tgt = int(m.group(1), 16)
            elif mnem == "jsr":
                rm = re.search(r"@r(\d+)", ops)
                if rm and rm.group(1) in loads:
                    tgt = loads[rm.group(1)]
            if tgt is not None and tgt in startset and tgt not in seen_edges:
                seen_edges.add(tgt)
                indeg[tgt] += 1
            pc += 2
    return indeg


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "1ST_READ.PRG"
    m = json.load(open(os.path.join(REPO, "build/analysis",
                                    f"{target}.map.json")))
    insn_map = load_insns(target)
    starts = sorted(f["vma"] for f in m["functions"])
    ev = {f["vma"]: f["evidence"] for f in m["functions"]}
    indeg = caller_counts(starts, insn_map)

    print(f"# {target} function inventory (Bucket 4 STOP 1, reachability-merged).")
    print("# Our analysis only: addresses/sizes/evidence — no Sega bytes.")
    print(f"# Regenerable: python3 tools/sh2_map.py {target} && "
          f"python3 tools/inventory_tsv.py {target}")
    print(f"# Detector seeded {m['seeds_before_merge']} starts; "
          f"{m['seeds_merged']} interior over-seeds (prologue tails / mid-fn")
    print("# arg spills) merged by reachability (Finding 1 fix). "
          f"Corrected inventory: {len(starts)}.")
    print("# size = owned span (flow_extent capped at next start); callers =")
    print("# in-degree over bsr + pool-resolved jsr edges. evidence: "
          "entry|prologue|bsr|jsr-pool|jmp-pool|ptr32")
    print("# vma\tsize\tcallers\tevidence")
    for i, s in enumerate(starts):
        nxt = starts[i + 1] if i + 1 < len(starts) else m["vma_base"] + m["size"]
        size = min(flow_extent(s, insn_map), nxt) - s
        chain = "+".join(e for e in EV_ORDER if e in ev[s])
        print(f"0x{s:07x}\t{size}\t{indeg[s]}\t{chain}")


if __name__ == "__main__":
    main()
