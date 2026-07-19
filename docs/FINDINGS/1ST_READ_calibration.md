# Bucket 3 calibration campaign — results & forecast

**Date:** 2026-07-19
**Sample:** 40 functions, `tools/campaign_select.py` seed 3 (stratified random
by span over the 1,451 prologue-confirmed seeds in `unattempted` segments),
boundary-corrected. Full list + per-function classification:
`config/targets/1ST_READ.campaign.tsv`. Per-attempt log: reproduced below
from `build/campaign_log.tsv` (regenerable; each match/attempt re-runnable via
`tools/try_match.sh <vma> --size N [--src ...]`).

**Headline: the campaign's dominant output is structural, not a match count.**
It established that the current per-function inventory cannot be matched
function-at-a-time, and *why* — three independent obstacles, each measured.
The match samples confirm that where a function *is* isolatable, the residual
is always a known drift family (schedule/register), never anything new.

## The three structural obstacles (measured on n=40)

| obstacle | count | consequence |
|---|---|---|
| **isolated-ok** (no ext-bsr, local pool only) | **9 (22.5%)** | matchable as a standalone unit |
| **needs multi-fn unit — external `bsr`** | 19 (47.5%) | calls neighbour(s); PC-relative displacement only reproducible by compiling the cluster together |
| **needs multi-fn unit — shared/distant pool** | 12 (30%) | loads a constant from a pool >64 B past its own code; pool placement (hence the load's PC displacement) is a translation-unit property |

**Only 22.5% of small functions are matchable in isolation.** The unit of
matching is the translation unit — see
`docs/FINDINGS/1ST_READ_translation_unit_structure.md`. Separately, **7/40
(17.5%) of the detector's seeds were mis-split prologue tails** (Finding 1);
the ~3,600 inventory count is inflated and the boundary detector needs the
`sts.l-pr-not-at-head` fix before a Bucket-4 scale campaign (prerequisite).

## Isolated-arm results (the clean signal)

Of the 9 isolated-ok, the three with standard calling convention and clean
structure were run to a verdict; the other six are entangled (2 inherited-
register fragments — read r2/r14 before writing, a non-standard convention or
residual mis-boundary; 1 tiny function whose 4-byte pool read crosses into its
neighbour; 3 large 338–990 B functions, deferred).

| function | size | shapes | verdict | residual family |
|---|---|---|---|---|
| `0x06014608` (switch dispatcher) | 90 B | 1 | **MATCHED** (sha256-proven) | — |
| `0x06014f70` GetCellAtWorldPos | 132 B | 3 | attempted | **#3 schedule** — 4 B: which arg-load fills the `jsr` delay slot; else byte-exact |
| `0x06014d14` (grid-cell walk) | 108 B | 6 | attempted | **#3 schedule** — loop rotation: original jumps to a bottom test with a mid-function pool, R31 top-tests |

**Every residual fell inside the known idiom families (§4) — no escalation
trigger fired.** Both near-misses are family #3 (instruction scheduling): the
same drift class Bucket 0.5 and the SEGALOGO unit attributed to the R31-vs-1997
compiler-version gap. The `0x06014f70` residual is 4 bytes on 132 — a single
delay-slot coin-flip from byte-identity.

**Two rates, and the distinction that matters:**
- **R31-exact isolated rate: 1/3** (n=3, tiny — a floor, not a forecast).
- **Structural-correctness rate: 3/3** — every attempt produced correct C whose
  only residual is a bounded, known drift family. This is the load-bearing
  number: the decompilation is *right*; the bytes differ only by compiler
  scheduling/register choices R31 makes differently from PDS's compiler.

## Multi-fn arm (77.5% of the sample)

Not run to byte-identity this session: the smallest candidate (`0x06039ba8`,
24 B) already requires reconstructing its whole pool-sharing cluster (its
shared pool sits +0x104 past its start, implying ~260 B of preceding code /
several functions), not just a caller+callee pair. **Effort multiplier is
large and the true unit is the pool cluster.** This is the measured finding
for the arm: multi-fn matching is a translation-unit reconstruction problem,
and its rate must be measured on reconstructed clusters (Bucket 4 tooling),
not estimated from isolated functions. Flagged as such in both forecasts.

## Forecast for 1ST_READ (drives the permuter decision & Bucket 4)

Caveats first: n is tiny (3 completed attempts), the ~3,600 function count is
inflated ~15–20% by over-seeding, and 77.5% of functions need machinery that
does not exist yet. These are order-of-magnitude planning numbers, not
promises.

- **Isolated-function floor (optimistic):** ~22.5% of functions are isolatable;
  of those, structural correctness looks high but R31-exact matches are gated
  by family-#3/#4 scheduling drift. Without a permuter, expect frequent
  near-misses even on isolatable functions → a *low* exact-match yield, high
  attempted yield.
- **Multi-fn-unit model (realistic, the one Bucket 4 runs on):** the majority
  case. Requires translation-unit reconstruction (cluster by `bsr` edges +
  shared-pool membership), then matching the cluster. Rate unmeasured until the
  reconstruction tooling exists; the `bsr`/pool clustering signal to build it
  is already in hand (`tools/fn_extent.py`).

## Permuter decision input (formal re-ask deferred to STOP 3)

**The evidence points toward a permuter being high-value.** Every residual in
the campaign is a schedule (#3) or register (#4) permutation — precisely the
search space `decomp-permuter` explores. A permuter would convert the
"structurally correct, drift-near-miss" majority (3/3 of attempts here) into
exact matches without waiting for the 1997 compiler to surface. Recommendation
for the STOP 3 decision: **adopt the permuter**, scoped to families #3/#4, once
the translation-unit reconstruction (Bucket 4) provides correctly-bounded
units to permute. Permuter-before-boundaries would be premature — it cannot fix
a wrong-boundary or wrong-pool-placement unit.

## Method integrity

All proof values are tool-generated (`try_match.sh` computes and prints the
manifest record on a match; §5). The one match (`0x06014608`) is recorded in
`config/targets/1ST_READ.yaml` with its tool-emitted sha256; the two attempts
carry residual analyses here, not manifest `matched` claims.
