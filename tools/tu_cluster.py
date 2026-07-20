#!/usr/bin/env python3
"""Translation-unit membership detection (Bucket 4 STOP 1, deliverable 2).

A function cannot be matched in isolation when (a) it calls a neighbour via a
PC-relative `bsr` (the displacement is fixed by the two functions' relative
placement) or (b) it loads a constant from a literal pool that other functions
also draw from (the pool's placement, hence every load's PC displacement, is a
property of the whole group). The matchable unit is therefore the closure of a
seed under BOTH relations.

This computes that closure:
  - bsr edge:   f -> g if f's flow extent contains `bsr g` (g in file range)
  - pool share: f and g belong together if a literal-pool longword that f
                references lies in a pool run that g also references, or that
                lies between two functions both of which reference the run.

The unit's span is [min start, max code/pool end); a unit is "closed" when no
member references a pool word or bsr target outside that span, and no outside
function references a pool word inside it. Emits the ordered member list and
the exact byte span to hand to try_match as one compile.

Usage: python3 tools/tu_cluster.py <seed_vma> [more seeds...]
       python3 tools/tu_cluster.py --smallest-internal-bsr   (survey)
"""
import json
import os
import re
import sys
import bisect

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prg import REPO
from sh2_map import flow_extent

VMA = 0x06006000
DISASM = os.path.join(REPO, "build/analysis/1ST_READ.PRG.disasm.txt")
MAP = os.path.join(REPO, "build/analysis/1ST_READ.PRG.map.json")
LINE = re.compile(r"^\s*([0-9a-f]+):\s+[0-9a-f]{2} [0-9a-f]{2}\s+(\S+)\s*(.*)")
POOL_LD = re.compile(r"mov\.[lw]\s+(0x[0-9a-f]+),r\d+")
MOVA = re.compile(r"mova\s+(0x[0-9a-f]+),r0")


def load():
    insn = {}
    with open(DISASM) as f:
        for line in f:
            m = LINE.match(line)
            if m:
                insn[int(m.group(1), 16)] = (m.group(2), m.group(3))
    mp = json.load(open(MAP))
    starts = sorted(f["vma"] for f in mp["functions"])
    poolw = {int(a, 16): w for a, w in mp["pool_widths"].items()}
    return insn, starts, poolw, mp["vma_base"] + mp["size"]


def refs_of(start, insn):
    """(bsr targets, pool addresses referenced) within start's flow extent."""
    end = flow_extent(start, insn)
    bsrs, pools = set(), set()
    pc = start
    while pc < end:
        if pc not in insn:
            pc += 2
            continue
        mn, ops = insn[pc]
        if mn == "bsr":
            m = re.match(r"(0x[0-9a-f]+)", ops)
            if m:
                bsrs.add(int(m.group(1), 16))
        pm = POOL_LD.match(f"{mn} {ops}") or MOVA.match(f"{mn} {ops}")
        if pm:
            pools.add(int(pm.group(1), 16))
        pc += 2
    return end, bsrs, pools


def owner(addr, starts):
    """Function start that owns code address `addr` (largest start <= addr)."""
    i = bisect.bisect_right(starts, addr) - 1
    return starts[i] if i >= 0 else None


def build_relations(insn, starts, poolw, endfile):
    """Precompute, for the whole file: the UNDIRECTED bsr adjacency (f~g if
    either calls the other with an in-range PC-relative bsr) and, for each
    maximal contiguous literal-pool run, the set of functions referencing it.
    Cross-TU bsr also appears as a compile-/link-time displacement, but a
    same-file call is the only kind we can reproduce by co-compiling, so we
    conservatively treat every in-range bsr as a same-unit edge."""
    ref = {s: refs_of(s, insn) for s in starts}
    adj = {s: set() for s in starts}
    for f in starts:
        _, bsrs, _ = ref[f]
        for t in bsrs:
            if VMA <= t < endfile:
                g = t if t in ref else owner(t, starts)
                if g is not None:
                    adj[f].add(g)
                    adj[g].add(f)
    # maximal contiguous pool runs
    pa = sorted(poolw)
    runs, i = [], 0
    while i < len(pa):
        lo = hi = pa[i]
        hi = pa[i] + poolw[pa[i]]
        j = i + 1
        while j < len(pa) and pa[j] == hi:
            hi = pa[j] + poolw[pa[j]]
            j += 1
        runs.append((lo, hi))
        i = j
    runlo = [r[0] for r in runs]

    def run_of(addr):
        k = bisect.bisect_right(runlo, addr) - 1
        return runs[k] if k >= 0 and runs[k][0] <= addr < runs[k][1] else None

    run_members = {}
    for f in starts:
        _, _, pools = ref[f]
        for p in pools:
            r = run_of(p)
            if r:
                run_members.setdefault(r, set()).add(f)
    # attach each function to the pool runs it shares
    fpruns = {s: set() for s in starts}
    for r, fs in run_members.items():
        for f in fs:
            fpruns[f].add(r)
    return ref, adj, fpruns, run_members, run_of


def close_unit(seed, insn, starts, endfile, rel=None, poolw=None):
    """Close `seed` under UNDIRECTED bsr adjacency + shared pool-run
    membership. Returns (sorted members, unit_start, unit_end)."""
    if rel is None:
        rel = build_relations(insn, starts, poolw, endfile)
    ref, adj, fpruns, run_members, run_of = rel
    members = {seed}
    changed = True
    while changed:
        changed = False
        for f in list(members):
            for g in adj[f]:
                if g not in members:
                    members.add(g)
                    changed = True
            for r in fpruns[f]:
                for g in run_members[r]:
                    if g not in members:
                        members.add(g)
                        changed = True
    ms = sorted(members)
    unit_end = 0
    all_pools = set()
    for m in ms:
        ce, _, pools = ref[m]
        unit_end = max(unit_end, ce)
        all_pools |= {p for p in pools if VMA <= p < endfile}
    if all_pools:
        unit_end = max(unit_end, max(all_pools) + 4)
    nxt_i = bisect.bisect_right(starts, ms[-1])
    nxt = starts[nxt_i] if nxt_i < len(starts) else endfile
    unit_end = min(unit_end, nxt) if unit_end <= nxt else unit_end
    return ms, ms[0], unit_end


def has_internal_bsr(members, rel):
    _, adj, _, _, _ = rel
    ms = set(members)
    return any(adj[f] & ms for f in members)


def main():
    insn, starts, poolw, endfile = load()
    rel = build_relations(insn, starts, poolw, endfile)
    if sys.argv[1:2] == ["--smallest-internal-bsr"]:
        seen = set()
        units = []
        for s in starts:
            if s in seen:
                continue
            ms, a, b = close_unit(s, insn, starts, endfile, rel)
            seen |= set(ms)
            if len(ms) >= 2 and has_internal_bsr(ms, rel):
                units.append((b - a, len(ms), a, b, ms))
        units.sort()
        print("# span\tnfns\tstart\tend\tmembers")
        for span, n, a, b, ms in units[:25]:
            print(f"{span}\t{n}\t0x{a:07x}\t0x{b:07x}\t"
                  f"{','.join(hex(x) for x in ms)}")
        return
    ref = rel[0]
    for arg in sys.argv[1:]:
        seed = int(arg, 16)
        ms, a, b = close_unit(seed, insn, starts, endfile, rel)
        print(f"unit seed 0x{seed:07x}: {len(ms)} members, "
              f"span [0x{a:07x},0x{b:07x}) = {b - a} bytes")
        for m in ms:
            ce, bsrs, pools = ref[m]
            print(f"  0x{m:07x} code_end 0x{ce:07x} "
                  f"bsr={[hex(x) for x in sorted(bsrs)]} "
                  f"pools={[hex(x) for x in sorted(pools)]}")


if __name__ == "__main__":
    main()
