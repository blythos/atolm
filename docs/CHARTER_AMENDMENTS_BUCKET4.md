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
