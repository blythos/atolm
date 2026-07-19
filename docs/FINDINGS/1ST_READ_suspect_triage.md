# 1ST_READ.PRG — 555-suspect triage (Bucket 3 deliverable 5)

**Date:** 2026-07-19
**Input:** the 555 Bucket-2 "suspects" (inventory functions with size ≤4 B and
0 callers), flagged as the uncertain tail of the segmentation.
**Method:** flow-reachability classification (`tools/fn_extent.py`); full
per-suspect record in `config/targets/1ST_READ.suspects.tsv`.

## Result: the suspect category is entirely a detector artifact

| class | count | % | meaning |
|---|---|---|---|
| **seed-artifact** | 439 | 79.1% | interior to a real function's flow extent — an over-seeded fragment, not a function |
| **real-function** | 94 | 16.9% | a valid function start the detector **undersized** (real flow extent > 8 B; size-4 was wrong) |
| **data** | 22 | 4.0% | pointer-table entry / non-code read as a function |

**Zero of the 555 are genuinely tiny functions.** Every suspect is either an
over-seeding artifact (79%), a real function the detector mis-sized (17%), or
data (4%). The "≤4 B, 0-caller" population does not exist as real code — it is a
readout of two detector defects.

## Interaction with the boundary-detector finding (as predicted at STOP 2)

This directly confirms and quantifies Finding 1
(`docs/FINDINGS/1ST_READ_translation_unit_structure.md`):

- **Over-seeding (439):** the detector seeds a bare `sts.l pr,@-r15` (and
  mid-function `mov.l rN,@-r15` argument spills) as function starts, creating
  fragments interior to the real function. These 439 are not functions and
  should be dropped.
- **Under-sizing (94):** the flipside — where the detector *did* find a real
  start, it sometimes assigned size 4 (stopping at the next spurious seed
  instead of the real `rts`). The real functions are larger; `tools/fn_extent.py`
  recovers their true extents.
- **Under-seeding (separate, from deliverable 4):** the prologue detector also
  *misses* save-less leaf functions entirely (both in-range Azel dispatch names
  were such). So the detector errs in all three directions.

## Corrected inventory count

Dropping the 439 seed-artifacts corrects the inventory:

- Bucket 2 reported **~3,626 functions**.
- **~3,187 after removing the 439 artifacts** (≈12% inflation from this
  population alone; the campaign's 17.5% mis-split sample rate suggests further
  inflation among the non-suspect `sts.l pr` seeds too — the true count is
  lower still, pending the Bucket 4 detector rewrite).

## New unclassified percentage

- **Suspect-level:** 555 → **0 unclassified** (100% triaged: 439 artifact / 94
  real / 22 data). The suspects were the dominant uncertain population; they are
  now resolved.
- **Byte-level:** the Bucket 2 map reported 4.1% unclassified. The 22 data and
  439 artifact suspects sat inside `unattempted` segments and are tiny
  (≤4 B each, ~2.2 KB total), so the byte-level figure barely moves; the value
  here is *function-level* — the inventory denominator is corrected and the
  uncertain-function tail is eliminated.

## Map update

The triage is recorded as a committed artifact
(`config/targets/1ST_READ.suspects.tsv`) rather than fragmenting the segment
map into 555 sub-4-byte segments (which would violate the coarse-map
convention — small in-code data/artifacts are noted, not cut out). The
actionable map change is deferred to the **Bucket 4 detector rewrite**, which
will regenerate the inventory with the reachability-merge fix and drop the 439
artifacts at the source. Until then, `config/targets/1ST_READ.functions.tsv`
carries a header note that its ≤4 B / 0-caller rows are triaged in
`.suspects.tsv` and are ~79% artifacts.
