# Proposed charter amendments — Bucket 4 STOP 1 (for human review)

**Status:** APPLIED 2026-07-20 (human approved at STOP-1 review). Blocks A–D
applied to `docs/PROJECT_CHARTER.md` (§0 flags, §4 permuter, §7 ledger ×2);
canonical flags updated in tools/try_match.sh, docs/WORKFLOW.md, config/README.md
and the two matched-unit records in config/targets/1ST_READ.yaml (re-verified);
superseded-count pointers added to the four historical FINDINGS. This document
is retained as the amendment ledger for the STOP-1 batch. Per the scribe rule
(charter §intro), the agent applies only human-approved verbatim blocks.

---

## Block A — corrected function inventory (supersedes every ~3,600/~3,187 cite)

The Bucket-4 boundary-detector rewrite (deliverable 1;
`docs/FINDINGS/1ST_READ_boundary_detector.md`) measured the corrected
1ST_READ inventory:

> **1ST_READ.PRG function inventory: 1,941 functions** (3,605 detector seeds −
> 1,664 interior over-seeds merged by reachability). Supersedes the Bucket-2
> ~3,626 count, the Bucket-3 ~3,187 estimate, and the "17.5% mis-split" sample
> figure. Every dropped seed is a mid-prologue `mov.l rN,@-r15` / `sts.l pr`
> push interior to a function with no hard boundary; all six ground-truth
> functions and all library placements survive. Residual seed artifacts (38
> size≤4 call-target/ptr32 seeds + 1 bsr-into-data) are a separate,
> order-of-magnitude-smaller class, deferred.

**Numbers to update where they appear** (flagged, not self-edited):
- `docs/PROJECT_CHARTER.md` §7 Bucket-3 entry ("corrected inventory ~3,187")
  and the Bucket-4 prerequisites entry ("17.5% of the campaign sample, 439 of
  the 555 suspects").
- `docs/CHARTER_AMENDMENTS_BUCKET3.md` Block A ("corrected inventory ~3,187")
  and the detector-fix block ("17.5% of the …").
- `docs/FINDINGS/1ST_READ_suspect_triage.md` (~3,626 / ~3,187 lines),
  `_translation_unit_structure.md` (~3,600), `_calibration.md` (~3,600, 1,451),
  `_azel_pilot.md` (3,626). These are historical FINDINGS; recommend a
  one-line "superseded: see 1ST_READ_boundary_detector.md (1,941)" pointer
  rather than rewriting the recorded analyses.

## Block B — §0 canonical toolchain: add `-macsave=0`

Deliverable 2 (`docs/FINDINGS/1ST_READ_proof_of_machine.md`) established that
SHC R31 defaults to saving MACL/MACH on clobber, but PDS's compiler treated
them as caller-saved. Proposed addition to the canonical invocation in
charter §0:

> Canonical flags: `-optimize=1 -speed -macsave=0`. `Macsave=0` selects
> caller-saved MACL/MACH, matching PDS's original compiler; without it R31
> emits a spurious 4-byte `sts.l macl / lds.l macl` frame around every
> function using `mul.l`/`mac` (a calling-convention mismatch, not codegen
> drift). The option only gates the save, so it is a no-op for functions
> without multiply/MAC and cannot regress existing matches. Evidence: with
> `-macsave=0`, `store_cksum` (0x06026f58) is byte-identical; the matched
> 0x06014608 (no multiply) is unchanged.

Standing watch unchanged: if an SHC 2.x–4.x binary surfaces, re-run the
Bucket-0.5 battery — `-macsave` behaviour is a candidate discriminator.

## Block C — §7 ledger: Bucket 4 STOP 1 outcome (GO/NO-GO)

> - **Bucket 4 STOP 1 — proof-of-machine:** boundary detector rewritten
>   (Finding 1 closed; inventory 1,941, Block A). Translation-unit membership
>   detection built (`tools/tu_cluster.py`: undirected `bsr` + shared-pool
>   closure). One closed unit (0x06026f3c, 3 functions, 74 B) reconstructed and
>   byte-diffed: **unit size and both intra-unit `bsr` displacements exact;
>   one of three functions byte-identical; residual = drift families #3/#4**
>   plus the `-macsave=0` calibration (Block B). Byte-diff verdict on the whole
>   unit: NON-MATCH → **STOP HARD** per the STOP-1 rule. The TU-bounding
>   premise is confirmed; whole-unit byte-identity under R31 alone is blocked
>   by pervasive, unshapeable #3/#4 drift. Strategy decision surfaced for the
>   human (permuter, Block D) — not decided by the byte-diff.

## Block D — §4 permuter decision: unit-level evidence

> The Bucket-4 STOP-1 unit adds translation-unit-level evidence to the STOP-3
> permuter recommendation: on a correctly-bounded unit whose cross-function
> `bsr` displacements and size are byte-exact, the *only* barrier to whole-unit
> byte-identity was #3 (schedule) / #4 (register-numbering) residual, confirmed
> unshapeable across 7+ source variants. This is precisely `decomp-permuter`'s
> search space. Recommendation stands: adopt the permuter scoped to #3/#4 once
> TU reconstruction feeds it correctly-bounded units — which STOP 1 now
> demonstrates it can.

---

# STOP-3 blocks (PROPOSED — for human review at this checkpoint)

**Status:** PROPOSED. Not applied. These supersede Block D's provisional lean
(the STOP-2/2.5 evidence reversed it). Apply verbatim only on approval.

## Block E — §7 ledger: Bucket 4 STOP 2 / 2.5 / 3

> - **Bucket 4 STOP 2 — proof-of-machine tooling + TU-position finding:**
>   reconstruction tooling landed (`tools/tu_cluster.py` `minimal_unit`,
>   `tools/tu_build.py` per-member byte-diff; scoped permuter `tools/permute.py`).
>   **Discovery: SHC codegen is translation-unit-context-dependent** — identical
>   source compiles to different deterministic schedules/registers by TU
>   position (three identical functions → three schedules; 0x06030f42 reachable
>   only at a non-first position). A third TU dependence beyond `bsr`
>   displacement and pool placement. New match: 0x06007788. See
>   docs/FINDINGS/1ST_READ_tu_position_dependence.md.
> - **Bucket 4 STOP 2.5 — A/B/C classification:** three-way matchability split
>   (A position-robust / B TU-context-dependent, R31-reachable / C
>   version-blocked candidate). Measured 6:2:3 on n=11 (size-adjusted ~47/21/32;
>   C is an upper bound on truly-blocked). `tools/classify_abc.py`
>   (measurement only). See docs/FINDINGS/1ST_READ_abc_classification.md.
> - **Bucket 4 STOP 3 — forecast & decisions (2026-07-20):** two ceilings vs
>   1,941 — **Release31-reachable now (A+B): ≥~65%, ~1,270 functions (lower
>   bound)**; **with the mid-1997 SHC (A+B+C): ~≥95%, the full inventory.**
>   Decisions: (1) **do not adopt decomp-permuter** — residuals are context- or
>   version-driven, not source-permutable; (2) **adopt TU-ordered reconstruction
>   as the scale-out unit; defer any context permuter** behind a measured
>   cost trigger; (3) **model tiering** — class A safe on the cheap tier
>   (try_match byte-proof, no judgment), B on the capable tier, C routed to the
>   compiler hunt. See docs/FINDINGS/1ST_READ_bucket4_forecast.md.

## Block F — §4: the position-dependence finding + two-ceiling forecast

> **SHC codegen is translation-unit-context-dependent (Bucket 4 STOP 2).** The
> same function source compiles to different deterministic instruction
> schedules and register allocations depending on the functions preceding it in
> the translation unit. Consequence: matchability is a three-way split, not
> two — **A** position-robust (matches isolated), **B** context-dependent
> (matches once its TU is reconstructed in order; Release31-reachable), **C**
> version-blocked (needs the mid-1997 SHC). Measured A:B:C ≈ 47:21:32
> (size-adjusted; C an upper bound). **Two ceilings vs the 1,941 inventory:
> Release31 reaches ≥~65% today (A+B, a lower bound); the period compiler
> reaches ~all of it.** The matching unit is therefore the *ordered* translation
> unit, and the mid-1997 SHC hunt is the single highest-leverage external
> dependency (it alone unlocks the ~32% class-C population).

## Block G — §4 permuter decision, REVISED (supersedes the Bucket-3 conditional and Block D)

> **decomp-permuter: not adopted (Bucket 4 STOP 3).** The Bucket-3 conditional
> ("adopt scoped to #3/#4 if Bucket 4 delivers bounded TUs") is resolved
> NEGATIVE: bounding was delivered, but the #3/#4 residuals proved to be
> dominantly translation-unit-*context*-driven (class B) or version-blocked
> (class C), not source-permutable — 570+ source variants closed essentially
> none of the hard residuals. A source-level permuter cannot model TU context
> and cannot reach the version wall, so its addressable population is a small
> minority. The lever that actually converts B residuals is **TU-ordered
> reconstruction** (adopted as the scale-out unit), and the lever for C is the
> **period compiler**. Any context/position-aware permuter is deferred behind a
> measured cost trigger (drift-guard 7).

## Block H — CLAUDE.md scope-ban update (mirror; apply to the repo CLAUDE.md)

> Replace the "PERMUTER remains deferred pending the human decision at STOP 3"
> clause with: "PERMUTER decision made at STOP 3: decomp-permuter NOT adopted
> (residuals are TU-context/version-driven, not source-permutable). Scale-out
> unit is the TU-ordered reconstruction (tu_cluster/tu_build). Any context/
> position-aware permuter is deferred behind a measured cost trigger." The
> dedup/similarity-clustering item may move from banned to permitted for Bucket 4
> (templated-overlay dedup is now expected-high-value), at the human's option.

## §8 ritual checks (this checkpoint)

- **Attribution:** ATTRIBUTION_AND_FINDINGS.md finding 6 carries the
  position-dependence finding (STOP 2, added this bucket); the SYSROF/ELF
  object-format dating heuristic (finding 1c/1a) is already folded in (human
  commit 76a3ffe). Recommend a one-line A/B/C + two-ceiling pointer in finding 6
  (staged below, Block I).
- **Document-ownership registry (§9):** new artifacts are covered by existing
  generic rows — FINDINGS docs (owned by the discovering session): boundary
  detector, proof-of-machine, tu_position_dependence, abc_classification,
  bucket4_forecast; tools (tu_cluster, tu_build, permute, inventory_tsv,
  classify_abc, sh2_map); this amendments file is the Bucket-4 amendment ledger.
  No new registry row required; confirmed covered.
- **CLAUDE.md / settings.json:** unchanged rules still hold except the permuter
  clause (Block H) and the inventory number (now 1,941, applied STOP 1).

## Block I — attribution finding 6, one-line forecast pointer

> *(Bucket 4 STOP 2.5/3: matchability is a three-way split — A position-robust,
> B TU-context-dependent (Release31-reachable), C version-blocked. Measured
> A:B:C ≈ 47:21:32 (size-adjusted). Two ceilings vs 1,941: Release31 reaches
> ≥~65% now, the mid-1997 SHC reaches ~all. See
> docs/FINDINGS/1ST_READ_abc_classification.md, 1ST_READ_bucket4_forecast.md.)*
