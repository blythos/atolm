#!/usr/bin/env python3
"""US call graph of 1ST_READ.PRG from the disassembly (Bucket 3 deliverable 4).

For each function (flow extent via fn_extent), collect its call targets:
  - `bsr` (PC-relative) -> absolute target
  - `jsr @Rn` where Rn was loaded from a literal pool with an in-range value
    (resolved by tracking the most recent mov.l pool load per register)
Emits caller -> [callees] as JSON and (optionally) a per-function callee set
keyed by address. Callees outside the file range (overlay/library thunks) are
kept as-is; they are still identity signals for structural matching.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fn_extent
from prg import REPO

VMA = 0x06006000
DISASM = os.path.join(REPO, "build/analysis/1ST_READ.PRG.disasm.txt")
LINE = re.compile(r"^\s*([0-9a-f]+):\s+([0-9a-f]{2} [0-9a-f]{2})\s+(\S+)\s*(.*)")
POOL_LD = re.compile(r"mov\.l\s+0x[0-9a-f]+,r(\d+)\s*!\s*([0-9a-f]+)")


def load_lines():
    rows = {}
    with open(DISASM) as f:
        for line in f:
            m = LINE.match(line)
            if m:
                rows[int(m.group(1), 16)] = (m.group(3), m.group(4))
    return rows


def function_starts():
    seeds = sorted(set(int(l.split("\t")[0], 16)
                       for l in open(os.path.join(REPO,
                       "config/targets/1ST_READ.functions.tsv"))
                       if not l.startswith("#") and len(l.split("\t")) >= 2))
    return seeds


def build(rows, insns):
    starts = function_starts()
    startset = set(starts)
    graph = {}
    for s in starts:
        code_end, *_ = fn_extent.extent(s, insns)
        loads = {}          # reg -> last pool value
        callees = []
        pc = s
        while pc < code_end:
            if pc not in rows:
                pc += 2
                continue
            mnem, ops = rows[pc]
            pm = POOL_LD.search(f"{mnem} {ops}")
            if pm:
                loads[pm.group(1)] = int(pm.group(2), 16)
            if mnem == "bsr":
                m = re.match(r"(0x[0-9a-f]+)", ops)
                if m:
                    callees.append(int(m.group(1), 16))
            elif mnem == "jsr":
                rm = re.search(r"@r(\d+)", ops)
                if rm and rm.group(1) in loads:
                    callees.append(loads[rm.group(1)])
            pc += 2
        graph[s] = sorted(set(callees))
    return graph, startset


def main():
    rows = load_lines()
    insns = fn_extent.load_disasm()
    graph, startset = build(rows, insns)
    out = os.path.join(REPO, "build/analysis/1ST_READ.callgraph.json")
    json.dump({f"0x{k:07x}": [f"0x{c:07x}" for c in v]
               for k, v in graph.items()}, open(out, "w"), indent=0)
    edges = sum(len(v) for v in graph.values())
    resolved_internal = sum(1 for v in graph.values() for c in v
                            if c in startset)
    print(f"callgraph: {len(graph)} functions, {edges} call edges, "
          f"{resolved_internal} resolve to a known function start")
    print(f"callgraph: written to {out}")


if __name__ == "__main__":
    main()
