#!/usr/bin/env python3
"""Flow-based function extent finder (Bucket 3 campaign; Bucket 4 detector seed).

The sh2_map seed detector over-seeds function starts (bare `sts.l pr` that is
really a prologue tail; mid-function `mov.l rN,@-r15` argument spills that look
like prologue pushes), so neither the inventory's next-seed span nor Ghidra's
seeded sizes give correct function extents. This computes the true code extent
by REACHABILITY: sweep instructions from the start following fall-through and
intra-function branches, treating calls (bsr/jsr) as non-extending, stopping
paths at rts/rte. Trailing literal pools are naturally excluded (not reachable
as instructions). Returns the code end; the matching size (code + owned pool)
is confirmed empirically by try_match.

Also classifies calls: bsr targets outside [start, code_end) are external
(PC-relative calls into neighbouring functions → the function needs a
multi-function translation unit to match, see
docs/FINDINGS/1ST_READ_translation_unit_structure.md).

Usage: python3 tools/fn_extent.py <vma> [<vma> ...]
       python3 tools/fn_extent.py --campaign   (reclassify the 40)
"""
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prg import REPO

DISASM = os.path.join(REPO, "build/analysis/1ST_READ.PRG.disasm.txt")
LINE = re.compile(r"^\s*([0-9a-f]+):\s+[0-9a-f]{2} [0-9a-f]{2}\s+(\S+)\s*(.*)")

# delayed-branch mnemonics: the following 2-byte slot is part of this function
DELAYED = {"bra", "bsr", "braf", "bsrf", "jmp", "jsr", "rts", "rte",
           "bt.s", "bf.s", "bt/s", "bf/s"}
COND = {"bt", "bf", "bt.s", "bf.s", "bt/s", "bf/s"}
CALL = {"bsr", "jsr", "bsrf", "jsrf"}


def load_disasm():
    insns = {}
    with open(DISASM) as f:
        for line in f:
            m = LINE.match(line)
            if m:
                insns[int(m.group(1), 16)] = (m.group(2), m.group(3))
    return insns


def branch_target(ops):
    m = re.match(r"(0x[0-9a-f]+)", ops)
    return int(m.group(1), 16) if m else None


POOL_LOAD = re.compile(r"mov\.[lw]\s+(0x[0-9a-f]+),r\d+")


def extent(start, insns):
    """Return (code_end, external_bsr_targets, ncalls, nbranches, pool_targets)."""
    seen = set()
    work = [start]
    code_end = start
    ext_bsr = set()
    pool_targets = set()
    ncalls = nbranches = 0
    while work:
        pc = work.pop()
        if pc in seen or pc not in insns:
            continue
        seen.add(pc)
        mnem, ops = insns[pc]
        pm = POOL_LOAD.match(f"{mnem} {ops}")
        if pm:
            pool_targets.add(int(pm.group(1), 16))
        end = pc + 2
        if mnem in DELAYED:
            end = pc + 4  # include delay slot
        code_end = max(code_end, end)
        tgt = branch_target(ops)
        if mnem in CALL:
            if mnem == "bsr" and tgt is not None:
                ncalls += 1
                # classified against final code_end after sweep; collect for now
                ext_bsr.add(tgt)
            else:
                ncalls += 1
            work.append(pc + 4)                 # return lands after delay slot
        elif mnem in COND:
            nbranches += 1
            if tgt is not None:
                work.append(tgt)
            work.append(end)                    # fall through (after slot if .s)
        elif mnem == "bra":
            nbranches += 1
            if tgt is not None:
                work.append(tgt)                # unconditional; no fall-through
        elif mnem in ("rts", "rte"):
            pass                                # path ends
        elif mnem in ("jmp", "braf", "bsrf"):
            pass                                # indirect; path ends here
        else:
            work.append(end)                    # ordinary fall-through
    # reclassify bsr targets now that code_end is known
    external = {t for t in ext_bsr if not (start <= t < code_end)}
    # pool entries within a small window past code_end are the function's OWN
    # trailing pool (local, matchable in isolation); anything further is a
    # shared/distant pool whose PC-relative displacement can't be reproduced
    # standalone.
    distant_pool = {t for t in pool_targets if t >= code_end + 64 or t < start}
    return code_end, external, ncalls, nbranches, distant_pool


def main():
    insns = load_disasm()
    if sys.argv[1:] == ["--campaign"]:
        rows = [l.rstrip().split("\t") for l in
                open(os.path.join(REPO, "config/targets/1ST_READ.campaign.tsv"))
                if not l.startswith("#")]
        addrs = [(int(r[1], 16)) for r in rows]
    else:
        addrs = [int(a, 16) for a in sys.argv[1:]]
    print("# vma\tcode_end\tsize\tcalls\tbranches\text_bsr\tdistant_pool\tclass")
    n_iso = n_multi = n_pool = 0
    for a in addrs:
        ce, ext, nc, nb, pool = extent(a, insns)
        if ext:
            cls = f"multi-fn:bsr({len(ext)})"; n_multi += 1
        elif pool:
            cls = f"multi-fn:pool({len(pool)})"; n_pool += 1
        else:
            cls = "isolated-ok"; n_iso += 1
        print(f"0x{a:07x}\t0x{ce:07x}\t{ce - a}\t{nc}\t{nb}"
              f"\t{len(ext)}\t{len(pool)}\t{cls}")
    print(f"# isolated-ok {n_iso}, multi-fn(bsr) {n_multi}, "
          f"multi-fn(shared-pool) {n_pool}")


if __name__ == "__main__":
    main()
