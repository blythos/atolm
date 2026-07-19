# Azel structural-matching pilot — yield report (Bucket 3 deliverable 4)

**Date:** 2026-07-19
**Bounded:** one session; target ≥100 new hypothesis-azel names for 1ST_READ
via call-graph propagation from the 22 known JP/US pairs + 60 library-
identified anchors. **Report yield and stop.**

## Yield: 2 confident names for 1ST_READ (target not met) + 141 overlay names harvested

The ≥100 target was **not met for 1ST_READ**, and the reason is itself the
finding: the productive Azel naming signal is address-annotated dispatch
tables, which are almost entirely in *overlays*, not the resident 1ST_READ
image; and call-graph propagation from the current anchor set does not
transfer into 1ST_READ.

### What worked: Azel's script-dispatch tables (direct address→name)
yaz0r/Azel registers overlay script functions in tables of the form
`overlayScriptFunctions.m_zeroArg[0x0600cddc] = {&getNpcData5E, "getNpcData5E"}`
— **143 explicit address→name pairs.** These are the reliable signal (explicit
address annotations, not fuzzy structural guesses). But:
- **141 of 143 are overlay addresses** (outside 1ST_READ's 0x06006000–0x06043e12).
  Captured as `config/azel_overlay_dispatch.tsv` — a **Bucket 4 overlay-naming
  resource** (44 in the 0x6070000 overlay, 60 in 0x6050000, 28 in 0x6090000, …).
- **2 are in 1ST_READ range** and are real functions: `getNpcData5E`
  (0x0600cddc) and `playSoundEffect_bank5` (0x0602c308). Both are **leaf
  functions the prologue detector missed** (no callee-save registers — the
  documented detector blind spot), so they were absent from the seed
  inventory. Imported as `hypothesis-azel`.

### What did not work: call-graph propagation into 1ST_READ
Built the US call graph (`tools/callgraph.py`: 3,626 functions, 9,300 call
edges, 95% resolving to known starts) and an anchored-callee-signature matcher
(`tools/azel_propagate.py`: a US function's set of anchored callees matched
against the same names each Azel C++ function calls). Result: **236 US
functions carry an anchored-callee signature, but only 13 produced a unique
Azel match, and those collapse to ~2 real functions — all low-confidence and
polluted by the boundary-detector over-seeding.** None were imported.

Three compounding reasons, all informative:
1. **Anchor scarcity.** Only 19 azel anchors sit in 1ST_READ range, and most
   are called by few functions; distinctive multi-anchor signatures are rare.
2. **Reimplementation mismatch.** Azel is a behavioural reimplementation; its
   C++ call structure does not mirror the compiled binary's call graph closely
   enough for signature equality (charter §6 — Azel is identification
   reference, never a structural oracle).
3. **Boundary-detector pollution.** The over-seeding (Finding 1) fragments real
   functions into multiple seeds, so propagation "hits" are mostly duplicate
   fragments of one function, not distinct names.

String-reference matching was also tested (do Azel sources cite 1ST_READ's
distinctive strings — NAME_ENT, PANDRA_3_0, MENUBK, SEGALOGO): negligible
overlap, no function-level correspondence.

## Implications

- **The Azel naming payoff is a Bucket 4 event, not a 1ST_READ one.** The 141
  overlay dispatch names (`config/azel_overlay_dispatch.tsv`) become directly
  importable once those overlays are extracted and mapped as targets. This is
  the single highest-yield naming resource found and it is banked.
- **Call-graph propagation needs prerequisites before it is productive:** the
  boundary-detector fix (Finding 1, so seeds are real functions) and a larger
  in-range anchor set. Chicken-and-egg with matching progress; revisit in
  Bucket 4 with corrected boundaries.
- **Second detector blind spot recorded:** the prologue detector *misses* leaf
  functions with no callee-save (both in-range dispatch names were such — real
  functions absent from the inventory). Complements the *over*-seeding of
  Finding 1: the detector both over-seeds `sts.l pr` tails and under-seeds
  save-less leaves. Both belong in the Bucket 4 detector rewrite; the
  reachability-merge approach (Finding 1) plus seeding call targets that land
  mid-nothing would catch the leaves.

## Tooling committed (Bucket 4 seeds)
`tools/callgraph.py` (US call graph), `tools/azel_propagate.py` (signature
matcher), `config/azel_overlay_dispatch.tsv` (141 overlay + 2 resident names).
