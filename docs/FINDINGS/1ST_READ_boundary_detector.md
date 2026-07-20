# 1ST_READ.PRG — boundary-detector rewrite (Bucket 4 STOP 1, deliverable 1)

**Date:** 2026-07-20
**Fixes:** Finding 1 (function-boundary over-seeding), raised in
`1ST_READ_translation_unit_structure.md` and `1ST_READ_calibration.md`.

## What was wrong

The prologue scanner (`tools/sh2_map.py`) seeds a function start at the first
push of a callee-save run and at a bare `sts.l pr,@-r15`. SHC schedules
non-push instructions *between* the register pushes and the `pr` push, and
spills argument registers mid-body with the same `mov.l rN,@-r15` encoding.
Both reset the scanner's "previous push" context, so a later push in the *same*
prologue — or a mid-function spill — was decoded as a fresh start. The Bucket-3
campaign measured 17.5% of the sampled seeds as mis-split prologue tails; the
inflated inventory was ~3,600 (loosely corrected to ~3,187 by the 555-suspect
triage, which only removed size≤4/0-caller artifacts and never counted the
mid-prologue-push / prologue-tail over-seeds).

## The fix — reachability merge + hard-boundary rescue

Added as a post-processing pass in `sh2_map.py` (`merge_interior_seeds`,
`flow_extent`). For each seed in address order, compute its flow extent by
reachability (sweep fall-through + intra-function branches; calls are
non-extending; stop at `rts`/`rte`/indirect `jmp`/`braf`/`bsrf`; trailing
literal pools are unreachable and excluded). A seed is **dropped** iff **all
three** hold:

1. its evidence is exactly `{prologue}` — never a call target (`bsr`/`jsr-pool`/
   `jmp-pool`), `ptr32`, or `entry`; those carry independent corroboration and
   are always kept;
2. it lies strictly interior to a preceding kept seed's flow extent;
3. it is **not** at a hard boundary — i.e. not immediately after an
   unconditional delayed terminator (`rts`/`rte`/`jmp`/`braf`/`bsrf`, with an
   optional `nop` delay slot) and not immediately after pool/pad.

Rule 3 is the rescue: a real neighbour that happens to start inside a preceding
function's *reachable* extent (tail-call `bra`, shared epilogue) sits right
after a terminator or pool and is preserved. `bra` is deliberately excluded
from the rescue terminators — a seed right after a `bra` may be the branch's
delay-slot push (contamination), not a real start.

## Result — corrected inventory 1,941 (not ~3,187)

`python3 tools/sh2_map.py 1ST_READ.PRG`:

- **3,605 seeded → 1,664 interior over-seeds merged → 1,941 function starts.**
- **Every one of the 1,664 dropped seeds is a `mov.l rN,@-r15` or `sts.l pr`
  push** (tool-checked: zero non-push drops), interior to a function with no
  hard boundary before it — exactly the two Finding-1 shapes and nothing else.
- The regenerated map records the dropped seeds under `merged_seeds` for audit.

The corrected inventory is committed as `config/targets/1ST_READ.functions.tsv`
via a new deterministic distiller (`tools/inventory_tsv.py`; size = flow-extent
owned span, callers = bsr/jsr-pool in-degree — replacing the Bucket-2 Ghidra
body size, which carried the braf-flap nondeterminism). Median owned span 70 B;
size≤4 residual is 38 (down from 555), none of them prologue-only — they are
`ptr32`/`jsr-pool` call-target artifacts (a different, order-of-magnitude
smaller class), plus one `bsr`-into-data seed (0x6043bce). Deferred, not
prologue over-seeds.

**~3,187 was never the right number.** It was a loose upper bound. Two
independent methods (forward reachability; backward predecessor scan) converge
near ~1,900; a 3,187-function file would imply an implausible ~68-byte mean.
1,941 is the measured count.

## Ground-truth and library preservation (required confirmations)

- **All six ground-truth functions kept**: the five Bucket-0.5 anchors
  (0x06006622, 0x0600ada4, 0x060067f8, 0x06006764, 0x0603a9f4) and the matched
  0x06014608. Tool-checked against the regenerated map.
- **Library identification is unaffected.** `tools/libscan.py` resolves the 15
  SBL/CPK hits (60 API symbols) by fingerprint scan of the extracted PRG
  against the catalogue — it never consults the boundary map, so the detector
  change cannot regress it. Re-run confirmed the same result. Of the 14 unique
  detector-visible placements, all 13 that were ever seeded survive the merge
  (`cpk_deb` at 0x6042070 is an A_SH member the prologue scanner never seeded —
  found by fingerprint, not by the detector; unchanged).

## Reproduce

```
python3 tools/sh2_map.py 1ST_READ.PRG          # 1941 starts, 1664 merged
python3 tools/inventory_tsv.py 1ST_READ.PRG    # -> functions.tsv
python3 tools/tu_cluster.py <seed>             # closed translation unit
```

The inventory-count change (1,941, superseding ~3,626/~3,187/~3,600 and the
17.5% figure) is flagged for the charter-amendment batch in
`docs/CHARTER_AMENDMENTS_BUCKET4.md`, not self-applied.
