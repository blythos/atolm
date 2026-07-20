# 1ST_READ.PRG — A/B/C matchability classification (Bucket 4 STOP 2.5)

**Date:** 2026-07-20
**Purpose:** the position-dependence discovery (STOP 2) invalidated the old
two-way matchable/blocked split. This measures the **three-way** split the
forecast and the STOP-3 permuter decision now depend on.

## The three classes

- **A — position-robust:** matches in isolation or a minimal spatial unit
  (no scheduling freedom, or its freedom resolves to the shipped choice).
- **B — context-dependent:** does NOT match isolated, but R31 *can* emit the
  shipped bytes under some translation-unit context (proven by finding a
  context that produces them). Reachable; realizing it needs ordered-TU
  reconstruction.
- **C — version-blocked (candidate):** no context in the battery produces the
  shipped bytes. Candidate true-1997-compiler case.

## Method (reachability measurement, not a matching tool)

For each sampled function a semantically-correct C reconstruction is compiled
with the canonical flags. **A** and **B** are self-validating — they are only
assigned when an actual byte-identical result is produced (isolated for A; at
some TU context for B), so the reconstruction is proven correct by the match
itself. **C** requires a validity gate: the isolated compile must have the same
instruction multiset as the shipped bytes (differing only by schedule/register)
— otherwise the "non-match" is a bad reconstruction, not a version block. Two
sampled functions (0x602c704, 0x602fcc6) were **dropped** because their
reconstructions could not be made instruction-exact within the effort bound
(persistent compiler-inserted spill / extra instruction) — an honest exclusion,
and itself a data point on reconstruction cost.

Context is searched by realizing many TU positions in one compile (the target
function repeated behind growing, varied padding). C-candidates additionally
ran a deep battery (~130 contexts: 6 padding trajectories × 11 positions × 2
source shapes); cksum additionally has the 570-variant source sweep from STOP 2.

## Result — A:B:C = 6:2:3 on 11 rigorously classified functions

| function | size | structure | class |
|---|---|---|---|
| 0x06006622 | 18 | leaf, straight-line | A |
| 0x06007788 | 14 | leaf, 3 stores | A |
| 0x0600de4a | 16 | leaf, straight-line | A |
| 0x06014608 | 90 | fn-pointer calls | A |
| 0x06026f58 `store_cksum` | 22 | calls cksum | A |
| 0x0600dba4 | 24 | branch + loop | A |
| 0x06030f42 | 14 | loop | **B** |
| 0x06007796 | 12 | 3 stores + const | **B** |
| 0x06006764 | 20 | 1 branch | **C** |
| 0x0602af28 | 22 | copy loop (register #4) | **C** |
| 0x06026f3c `cksum` | 28 | loop + multiply | **C** |

**≈ 55% A : 18% B : 27% C.**

Structure is only a rough predictor: 0x0600dba4 has a branch *and* a loop yet is
A (its scheduling freedom resolves to the shipped choice), while the tiny
0x06030f42 loop is B. Scheduling freedom is necessary but not sufficient for
position-dependence.

## Caveats (bearing on how to read the ratio)

1. **Sample size 11**, short of the 15–20 target: rigorous *instruction-exact*
   reconstruction is the bottleneck (you must reconstruct correctly before you
   can classify at all), and 2 candidates were dropped for reconstruction
   incompleteness. Treat 6:2:3 as order-of-magnitude, not precise.
2. **Skewed small** (12–90 B). Large functions are under-represented and may
   behave differently (more scheduling freedom → plausibly more B/C).
3. **C is an upper bound on truly-blocked.** It means "no match found in the
   battery." The deep battery (2 of 3) and the 570-variant sweep (cksum) make
   these robust, but a still-larger or real-context search could move some
   C→B — the optimistic direction the STOP-2 finding predicts. The *true*
   version-blocked rate is ≤ 27%.

## Per-class effort (the forecast input)

- **A — cheapest, fully tooled.** Reconstruct the one function; verify
  standalone via `tools/try_match.sh`. Cost = decompilation of that function.
- **B — reachable, gated on ordered-TU reconstruction.** A B function matches
  only when its translation unit is reconstructed **in order** and co-compiled
  (`tools/tu_build.py` takes an ordered member list — tooled). There is no
  per-function trick and the synthetic-context probe is *not* a committable
  path (you cannot ship padding). So B's realized cost = reconstruct the whole
  ordered TU. That is cheap when the TU is small/self-contained and expensive
  when the function sits in a shared-leaf module TU (up to ~the whole module).
  B functions are **not individually verifiable** — this changes the workflow
  from function-at-a-time to TU-at-a-time.
- **C — blocked under R31.** Requires the mid-1997 SHC (charter §0 standing
  hunt); documented `attempted` with residual until it surfaces.

## Is class B tooled or hand-done? (explicit answer)

The **co-compile step is tooled** — `tu_build.py` reconstructs a unit from an
ordered member list and byte-diffs per member. What fixed 0x06030f42 in STOP 2
was a *synthetic* predecessor found by search, which **measures** reachability
but is **not** a repeatable production step (synthetic padding can't ship). The
repeatable production step for a class-B match is: reconstruct every member of
its TU in address order, then `tu_build`. That is tooled but its cost is the
whole TU, not one function. A deterministic "minimal real context" recipe does
not yet exist — building one (a context/position permuter) is the STOP-3
question, and this measurement is its target-population sizing: **~18% of
functions are class B**, i.e. the population a context-aware approach would
convert from "needs full-TU reconstruction" to "cheaper," and **~27% (upper
bound) are class C**, the population only a period compiler can reach.
