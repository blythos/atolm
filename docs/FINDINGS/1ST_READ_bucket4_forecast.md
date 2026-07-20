# 1ST_READ.PRG — Bucket 4 forecast & STOP-3 decisions

**Date:** 2026-07-20 (Bucket 4 STOP 3)
**Inputs:** corrected inventory 1,941 (STOP 1); TU-position-dependence (STOP 2);
A:B:C classification 6:2:3 (STOP 2.5); size-skew probe (this doc).

## Two ceilings, against the 1,941-function inventory

Every function is one of: **A** position-robust (matches isolated), **B**
context-dependent (matches once its TU is reconstructed in order — R31-reachable),
**C** version-blocked candidate (no R31 context found; needs the mid-1997 SHC).
A and B are both Release31-reachable **today**; C is the version wall.

### Size-skew correction (required — the sample was small functions)

The STOP-2.5 sample (n=11) spans 12–90 B. The inventory splits **62.2%
≤96 B** (1,207 fns, the sampled range) and **37.8% >96 B** (734 fns,
under-sampled). Larger functions have more scheduling freedom, so B and C
should rise with size. Partial validation this session:

- 0x06014608 (90 B) → **A**
- 0x06014f70 (132 B) → **C** (deep battery + arg-order shapes — a clean large
  non-A point)
- 0x06014d14 (108 B) → reconstruction not instruction-exact within bound
  (**a difficulty signal**: rigorous reconstruction cost itself rises with size)

One clean large point (132 B = C) plus the reconstruction-difficulty signal
**directionally confirm** the skew but do not measure the large-band ratio.
The forecast therefore uses the small-band ratio as measured and an *estimated,
wide-barred* large-band ratio, and never presents 55/18/27 as size-invariant.

| band | share | A | B | C | basis |
|---|---|---|---|---|---|
| ≤96 B | 62.2% | 55% | 18% | 27% | measured, n=11 (rough) |
| >96 B | 37.8% | ~35% | ~25% | ~40% | estimated, 1 validated point, wide bars |
| **weighted** | 100% | **~47%** | **~21%** | **~32%** | — |

### The two ceilings

- **Release31 ceiling (A+B, no new compiler): ~68%**, and because **C is an
  upper bound on truly-blocked** (context search is incomplete → some C are
  really B), this is a **lower bound**: **≥ ~65%, plausibly 70–80%.**
  ≈ **1,270 functions now-reachable (range ~1,180–1,510).**
- **With the mid-1997 SHC (A+B+C): ~≥95%**, effectively the full **1,941**
  (minus the ~15 already `library-identified` and any genuine oddity). C
  (~32%, ~620 fns) converts to reachable when the version drift disappears.

**Error bars are wide** (n=11 + 1 large point; order-of-magnitude planning
numbers). The load-bearing, robust facts are the *ordering* — A+B ≫ C — and the
direction — the true R31 ceiling is a lower bound, i.e. the news only gets
better with more search.

## Decision 1 — decomp-permuter (the Bucket-3 conditional): **DO NOT ADOPT**

The Bucket-3 conditional was "adopt decomp-permuter scoped to #3/#4 **if** Bucket 4
delivers correctly-bounded TUs." Bounding was delivered — but the STOP-2 evidence
**falsifies the value premise**: the #3/#4 residuals are dominantly **context-
driven (class B)** or **version-blocked (class C)**, not source-permutable. 570+
source variants closed essentially none of the hard residuals; what closed them
was **TU context** (a compiler-state axis decomp-permuter does not model) or
nothing (needs the compiler). A source permuter's addressable target — pure
source-reachable #3/#4 — is a small minority. **Recommendation: do not adopt
decomp-permuter.** This overturns the Bucket-3 conditional lean, on new evidence.

## Decision 2 — class-B tooling / context permuter: **DEFER; adopt TU-at-a-time instead**

Class B (~21%) is realized by reconstructing its whole TU **in order** and
co-compiling — which a full-PRG matching build does anyway. So **B functions
match "for free" under TU-ordered reconstruction**; they do not need a context
permuter to be matched, only to be matched/verified *without* reconstructing
their TU. A "minimal real committable TU context" recipe / context-aware
permuter therefore earns its cost only for (a) incremental B-verification and
(b) B functions in large shared-leaf TUs where full reconstruction is expensive.

**Recommendation:** adopt **translation-unit-ordered reconstruction as the
scale-out unit of work** (tools/tu_cluster.py `minimal_unit` for spatial
membership + address-order = the ordered TU; tools/tu_build.py co-compiles and
per-member-verifies). **Do NOT build the context permuter now** — defer it
behind a measured trigger: *if the first N real TUs show prohibitive cost for
large/shared-leaf units, revisit.* Consistent with charter drift-guard 7 (no
new infrastructure before the need is demonstrated).

## Decision 3 — model tiering (per-class effort now known)

- **Class A → cheapest tier is SAFE.** A matches are machine-verified by
  `try_match` (objective sha256 byte-proof, zero judgment). The STOP-2 tiering
  test confirmed it: the cheap tier (permute + try_match) produced a real,
  authority-verified match (0x06007788). Cheap-tier automation over class A is
  safe **because every claimed match is byte-proven, not judged** — a false
  positive cannot survive try_match (charter §5).
- **Class B → higher tier.** Requires TU reconstruction + ordering judgment;
  not individually verifiable. Reserve for the capable tier.
- **Class C → not tier-worthy.** Unreachable under R31; document `attempted`
  with residual and route to the compiler hunt, don't spend match effort.

## Consequences for the Bucket-4 plan

1. Scale-out is **TU-at-a-time**, not function-at-a-time: reconstruct a TU's
   members in address order, `tu_build`, land the A+B members, log C members as
   `attempted`.
2. The **overlay dedup/similarity-clustering** idea (charter §7 Bucket-4 sketch)
   gains value: templated overlays likely share TU structure, so a TU
   reconstructed once may match many.
3. The **mid-1997 SHC hunt** is now quantified: it is the only path to the
   ~32% (≈620-function) class-C population — the single highest-leverage
   external dependency. The §0 standing appeal is load-bearing, not incidental.
