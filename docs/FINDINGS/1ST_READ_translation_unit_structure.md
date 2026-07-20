# Bucket 4 structural input: the matching unit is the translation unit, not the function

> **Superseded count (Bucket 4 STOP 1, 2026-07-20):** inventory figures in this file (~3,600/~3,626/~3,187 functions, 17.5% mis-split, 1,451 population) predate the boundary-detector rewrite. The measured corrected inventory is **1,941**; see docs/FINDINGS/1ST_READ_boundary_detector.md. The structural conclusions here are unaffected.

**Date:** 2026-07-19 (Bucket 3 calibration campaign, structural finding)
**Status:** decision-grade; **the single most important result of Bucket 3.**
It redefines Bucket 4's unit of work and seeds a proposed charter amendment
at STOP 3 (new finding in §4; Bucket 4's plan reoriented around translation
units, not functions). This is a standalone structural finding, not a
campaign footnote.

## Finding

In a representative, boundary-corrected random sample of 40 small functions
(`config/targets/1ST_READ.campaign.tsv`, `tools/campaign_select.py` seed 3),
**21 of 40 (52.5%) make at least one PC-relative `bsr` call to a neighbouring
function** rather than only absolute pool-loaded (`jsr @Rn`) calls.

A PC-relative `bsr` encodes a *signed displacement to the callee*, resolved
by the assembler from the two functions' positions in the **same translation
unit**. To reproduce those bytes, the callee must sit at the exact same
displacement — which means the caller and callee must be compiled together,
in the same source file, in the same order. **A function that `bsr`s a
neighbour cannot be matched byte-identically in isolation**; its unit of
matching is the enclosing translation unit, not the single function.

By contrast, absolute calls (`mov.l #addr,Rn; jsr @Rn`, where `#addr` is a
link-time-fixed pointer materialised from the literal pool) *are* matchable
in isolation, because the pointer value is a constant independent of the
caller's placement.

## Why this matters for Bucket 4

The naïve decomp model — pick a function, match it, repeat — works for the
19/40 self-contained functions but **fails by construction for the 52.5%
majority**. Bucket 4's unit of work should be the **translation unit**:
group functions connected by PC-relative `bsr` edges, reconstruct the whole
group as one source file, and match the group's bytes together. The
calibration campaign (this bucket) measures both rates separately —
isolated-function match rate (optimistic floor) and multi-function-unit
match rate (the realistic model Bucket 4 runs on).

Corroborating structure: the SHC assembler resolves same-file `bsr` to a
direct displacement (charter §4), so the original build clearly compiled
these neighbour-clusters as single files. The `bsr` edges are a *direct
readout of the original source-file grouping* — a free translation-unit
segmentation signal for Bucket 4 (cluster the call graph by `bsr` edges;
`jsr`-pool edges cross unit boundaries, `bsr` edges stay within one).

## Method / reproducibility

`tools/campaign_select.py` emits a `standalone` column: `yes` when a function
has zero external `bsr` targets, `no-extbsr` otherwise. The classifier
disassembles each function's corrected extent and checks every `bsr`
displacement against the function's own `[start,end)`. Spot-check any
function with `tools/segment_report.py <vma>` plus
`tools/sh-elf.sh <dir> objdump -D -b binary -m sh2 -EB orig.bin`.

## Bucket 4 prerequisite: the function-boundary detector bug (Finding 1)

**Bug.** `sh2_map.py` seeds a bare `sts.l pr,@-r15` as a function start, but
SHC often schedules an instruction between the register push and the PR push
(e.g. `mov.l r14,@-r15; mov r4,r0; sts.l pr,@-r15`), so that `sts.l pr` is the
*tail* of a prologue that began a few bytes earlier. It also seeds
mid-function `mov.l rN,@-r15` argument spills as if they were prologue pushes.
Both create false function starts that (a) inflate the count and (b) truncate
the preceding function's span at the false start.

**Measured impact.** 7 of 40 sampled seeds (17.5%) were mis-split prologue
tails. The Bucket 2 inventory's ~3,600-function count is inflated by roughly
that fraction — the true function denominator is smaller. Match-rate
*fractions* stay sound, but any per-function *count*-based forecast is
optimistic and must be discounted ~15–20%.

**Fix approach (noted while fresh; a Bucket 4 prerequisite before any
scale-out campaign).** Do not classify a start from prologue-shape alone.
Instead run flow-reachability over all seeds (the algorithm is already
implemented in `tools/fn_extent.py`): compute each seed's reachable code
extent `[start, code_end)` following fall-through + intra-function branches,
calls non-extending, stopping at `rts`. **Any seed that lies strictly inside
another seed's `[start, code_end)` is not a real function start — drop it and
merge.** This subsumes both failure modes (prologue-tail `sts.l pr` and
mid-function spill pushes) with one reachability pass, and needs no
prologue-shape special-casing. `tools/campaign_select.py` already applies the
narrower prologue-tail correction for the campaign; the general
reachability-merge is the Bucket 4 detector rewrite.
