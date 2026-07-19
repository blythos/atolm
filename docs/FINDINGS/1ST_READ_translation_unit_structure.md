# 1ST_READ.PRG — the matching unit is the translation unit, not the function

**Date:** 2026-07-19 (Bucket 3 calibration campaign, structural finding)
**Status:** decision-grade; drives Bucket 4's unit of work.

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

## Related detector note (Finding 1, same campaign)

Seed anchoring: `sh2_map.py` seeds a bare `sts.l pr,@-r15` as a function
start, but SHC often schedules an instruction between the register push and
the PR push, so that `sts.l pr` is the *tail* of a prologue beginning a few
bytes earlier. **7 of 40 sampled seeds (17.5%) were such mis-split prologue
tails.** Consequence: the Bucket 2 inventory's ~3,600-function count is
inflated — the true function denominator is smaller, which makes every
match-rate forecast slightly optimistic in the count but the *fraction*
sound. Fixing the `sts.l-pr-not-at-head` case in `sh2_map.py` is a **Bucket 4
prerequisite**; `tools/campaign_select.py` already corrects it for the
campaign (folds a mis-split tail back into the preceding start when the gap
is prologue-only and rts-free).
