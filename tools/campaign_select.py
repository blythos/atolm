#!/usr/bin/env python3
"""Bucket 3 calibration-campaign candidate selection (reproducible).

Criteria (stated before the campaign, per the bucket brief):
- population: functions in config/targets/1ST_READ.functions.tsv whose
  start lies in an `unattempted` segment of the manifest (excludes all
  library-identified/candidate rows, the GCC pocket, data) AND whose
  evidence chain includes a detector-confirmed start (prologue or entry);
- span = distance to the next inventory start (the unit-owns-its-pools
  matching span; --size in try_match);
- stratified by span band, allocation proportional to the population
  (largest-remainder rounding), sampled with a fixed recorded seed —
  representative of small-function reality by construction, no
  cherry-picking.

Usage: python3 tools/campaign_select.py [--n 40] [--seed 3]
Prints a TSV; the committed copy is config/targets/1ST_READ.campaign.tsv.
"""
import argparse
import bisect
import struct
import random

import yaml

BANDS = ((16, 64), (64, 128), (128, 256), (256, 512), (512, 1 << 30))
VMA_BASE = 0x06006000

# Boundary correction (Bucket 3 finding): the sh2_map detector seeds a bare
# `sts.l pr,@-r15` (0x4f22) as a function start, but SHC often schedules an
# instruction between the register push and the pr push, so the pr push is
# really the tail of a prologue that began a few bytes earlier. Such a seed
# is a mis-split: a near-preceding seed, no rts between, prologue-only bytes
# in the gap. We fold it back into the true start. ~17.5% of small-function
# seeds are affected; correcting them is essential for honest sizes/tags.


def _hw(data, off):
    return struct.unpack(">H", data[off:off + 2])[0]


def _prologue_only(data, a, b):
    """True if [a,b) is only prologue-schedulable ops (pushes, sts.l pr,
    reg moves, small immediates) with no rts/branch."""
    for o in range(a - VMA_BASE, b - VMA_BASE, 2):
        h = _hw(data, o)
        if (h & 0xFF0F) == 0x2F06 or h == 0x4F22:      # mov.l R,@-r15 / sts.l pr
            continue
        if (h & 0xF00F) == 0x6003:                     # mov Rm,Rn
            continue
        if (h & 0xF000) in (0xE000, 0x7000):           # mov #imm / add #imm
            continue
        return False
    return True


def true_start(seed, seeds_sorted, data):
    """Correct a mis-split prologue-tail seed to the real function start."""
    i = bisect.bisect_left(seeds_sorted, seed)
    if i == 0 or _hw(data, seed - VMA_BASE) != 0x4F22:
        return seed
    prev = seeds_sorted[i - 1]
    if 0 < seed - prev <= 12 and _prologue_only(data, prev, seed):
        # no rts in the gap is implied by _prologue_only (rts=0x000b excluded)
        return prev
    return seed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=3)  # bucket number
    args = ap.parse_args()

    m = yaml.safe_load(open("config/targets/1ST_READ.yaml"))
    eligible = [(s["start"], s["end"]) for s in m["segments"]
                if s["state"] == "unattempted"]

    rows = []
    with open("config/targets/1ST_READ.functions.tsv") as f:
        for line in f:
            if line.startswith("#"):
                continue
            p = line.rstrip("\n").split("\t")
            if len(p) < 4:
                continue
            rows.append((int(p[0], 16), int(p[1]), int(p[2]), p[3]))
    rows.sort()

    pop = []
    for i, (vma, size, callers, ev) in enumerate(rows):
        off = vma - VMA_BASE
        if not any(a <= off < b for a, b in eligible):
            continue
        if "prologue" not in ev and "entry" not in ev:
            continue
        span = rows[i + 1][0] - vma if i + 1 < len(rows) else size
        if span < 16:
            continue
        pop.append((vma, size, span, callers, ev))

    by_band = {b: [] for b in BANDS}
    for r in pop:
        for lo, hi in BANDS:
            if lo <= r[2] < hi:
                by_band[(lo, hi)].append(r)
                break

    # largest-remainder proportional allocation
    total = sum(len(v) for v in by_band.values())
    quotas = {b: args.n * len(v) / total for b, v in by_band.items()}
    alloc = {b: int(q) for b, q in quotas.items()}
    rest = args.n - sum(alloc.values())
    for b in sorted(quotas, key=lambda b: quotas[b] - alloc[b], reverse=True)[:rest]:
        alloc[b] += 1

    rng = random.Random(args.seed)
    picked = []
    for b in BANDS:
        picked += rng.sample(by_band[b], alloc[b])

    # boundary-correct each selected seed and compute complexity on the
    # corrected extent. Selection itself is unchanged (stable sample of the
    # detector population); only match-time boundaries are fixed.
    data = open("extracted/1ST_READ.PRG", "rb").read()
    seeds_sorted = sorted(vma for vma, *_ in rows)
    true_seeds = sorted(true_start(s, seeds_sorted, data) for s in seeds_sorted)

    def complexity(start, end):
        calls = branches = far_bsr = 0
        for o in range(start - VMA_BASE, end - VMA_BASE, 2):
            h = _hw(data, o)
            if (h & 0xF0FF) == 0x400B or (h & 0xF0FF) == 0x402B:  # jsr/jmp @Rn
                calls += 1
            elif (h & 0xF000) == 0xB000:                          # bsr
                disp = h & 0x0FFF
                if disp & 0x800:
                    disp -= 0x1000
                tgt = o + 4 + disp * 2 + VMA_BASE
                calls += 1
                if not (start <= tgt < end):
                    far_bsr += 1
            elif (h & 0xFF00) in (0x8900, 0x8B00, 0x8D00, 0x8F00):  # bt/bf/bt.s/bf.s
                branches += 1
            elif (h & 0xF000) == 0xA000:                          # bra
                branches += 1
        if calls == 0:
            tag = "leaf-branch" if branches else "leaf"
        else:
            tag = "calls-branch" if branches else "calls"
        return tag, calls, branches, far_bsr

    print(f"# calibration campaign candidates: n={args.n} seed={args.seed}")
    print(f"# population {total} prologue-confirmed seeds in unattempted "
          f"segments; band allocation "
          f"{[f'{lo}-{hi}:{alloc[(lo,hi)]}' for lo,hi in BANDS]}")
    print("# boundaries corrected for mis-split prologue-tail seeds (sts.l pr "
          "seeded mid-prologue); span = to next corrected start.")
    print("# seed\ttrue_start\tspan\ttag\tcalls\tbranches\tstandalone\tcallers")
    for vma, size, span, callers, ev in sorted(picked):
        ts = true_start(vma, seeds_sorted, data)
        i = bisect.bisect_right(true_seeds, ts)
        end = true_seeds[i] if i < len(true_seeds) else ts + size
        tag, calls, br, far = complexity(ts, end)
        standalone = "yes" if far == 0 else "no-extbsr"
        corr = "" if ts == vma else f"<-0x{vma:07x}"
        print(f"0x{ts:07x}{corr}\t0x{ts:07x}\t{end - ts}\t{tag}\t{calls}"
              f"\t{br}\t{standalone}\t{callers}")


if __name__ == "__main__":
    main()
