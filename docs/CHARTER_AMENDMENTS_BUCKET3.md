# Proposed charter amendments — Bucket 3 close (for human review)

**Status:** PROPOSED. Per the scribe rule (charter §intro), the agent never
amends charter content on its own judgment; these blocks are applied verbatim
to `docs/PROJECT_CHARTER.md` only after approval at this STOP 3 review. Nothing
here is live until you apply it.

---

## Block A — §7 ledger, new "Closed" entry

> - **Bucket 3 — workflow at function scale:** CLOSED (2026-07-19). Library
>   identification: 15 SBL/CPK catalogue members fingerprinted in 1ST_READ
>   (5,056 B `library-identified`, 60 verified API symbols; sixth segment
>   state `library-identified` added, machine-enforced). Per-function workflow
>   formalized (docs/WORKFLOW.md; `tools/try_match.sh`; asm-differ adapted as
>   `tools/fndiff.sh`). Calibration campaign on a representative 40-function
>   sample: 1 exact match, 2 attempted (both drift-family #3), and the
>   structural results in Block B. Azel structural pilot (bounded): call-graph
>   propagation into 1ST_READ did not transfer (2 confident names via dispatch
>   tables; 141 overlay dispatch names banked for Bucket 4). 555-suspect triage:
>   79% seed-artifacts, 0 genuine tiny functions; corrected inventory ~3,187.

## Block B — §4, new confirmed finding (calibration + translation-unit structure)

> **The matching unit is the translation unit, not the function (Bucket 3
> calibration):** on a representative 40-function sample, only ~22.5% of small
> functions are matchable in isolation. ~77.5% require multi-function
> translation-unit reconstruction — 47.5% call a neighbour via PC-relative
> `bsr` (displacement is a translation-unit property), 30% load from a
> shared/distant literal pool (pool placement is a translation-unit property).
> Where a function is isolatable, every observed residual falls in a known
> compiler-drift family (instruction scheduling / register numbering): the
> decompilation is structurally correct, bytes differ only by Release31's
> codegen choices vs PDS's compiler. **This redefines Bucket 4's unit of work
> from the function to the translation unit** (cluster by `bsr` edges +
> shared-pool membership; `tools/fn_extent.py` carries the signal). Evidence:
> docs/FINDINGS/1ST_READ_translation_unit_structure.md, 1ST_READ_calibration.md.

## Block C — §3, formal per-function effort protocol (supersedes the interim bound)

> **Per-function effort protocol (Bucket 3, supersedes the interim bound in
> this section):** leaf functions — 5 source-shape attempts or 1 focused hour;
> functions with calls or branches — 8 shapes or 2 hours; whichever comes
> first. A "shape" is a structurally distinct source variant honestly aimed at
> the residual (renaming a variable is not a shape). On hitting the bound,
> classify the residual against the known idiom families (§4) and land the unit
> as `attempted` with a findings file. **A residual OUTSIDE the known families
> is escalated for human review, not filed** — it is new evidence about the
> compiler. The loop is documented in docs/WORKFLOW.md and is designed to be
> runnable by cheaper models (procedure + objective diff verdict + bounded
> effort + structured filing); campaign sessions may run at reduced model tier
> at the human's discretion.

## Block D — permuter decision record (§4 or §7 deferred-ledger, your placement)

> **Permuter decision (recorded Bucket 3 STOP 3):** the calibration evidence —
> every isolated-function residual is a schedule (#3) or register (#4)
> permutation, i.e. exactly `decomp-permuter`'s search space — supports
> adopting a permuter. **Decision: adopt the permuter, scoped to families
> #3/#4, AFTER Bucket 4 provides correctly-bounded translation units to
> permute.** Rationale for the ordering: a permuter cannot repair a
> wrong-boundary or wrong-pool-placement unit, so boundaries come first.
> (Previously human-deferred pending campaign data; the data now exists.)

## Block E — Bucket 4 prerequisites (§7 planned-Bucket-4 entry, addendum)

> **Bucket 4 prerequisites established by Bucket 3 (binding before scale-out):**
> (1) **Function-boundary detector rewrite** — the current detector both
> over-seeds (bare `sts.l pr` tails and mid-function spill pushes; 17.5% of the
> campaign sample, 439 of the 555 suspects were artifacts) and under-seeds
> (misses save-less leaf functions). Fix approach: reachability-merge — compute
> each seed's flow extent (`tools/fn_extent.py`) and drop any seed interior to
> another's extent; additionally seed save-less leaves reached as call targets.
> (2) **Translation-unit reconstruction** — cluster functions by `bsr` edges +
> shared-pool membership; match clusters, not functions. (3) The multi-fn match
> rate must be measured on reconstructed clusters, not estimated from isolated
> functions.

---

## Layer-3 / document-ownership check (this STOP, for the record)

- CLAUDE.md updated: the stale "NO asm-differ" ban replaced (asm-differ landed
  Bucket 3; permuter still deferred). Six-state vocabulary and the corrected
  ~3,187 count reflected in README.
- ATTRIBUTION_AND_FINDINGS.md refreshed (header → Buckets 0–3; new finding 6
  translation-unit; finding 3 count hedged). Owner: checkpoint attribution
  check.
- New standing documents created this bucket, each with a ritual owner:
  WORKFLOW.md (effort-protocol revisions at checkpoint); the five Bucket 3
  FINDINGS docs (discovering session at STOP); the committed `.tsv` artifacts
  (tool-generated: campaign_select.py / fn_extent.py / libscan.py). No
  owner-less document introduced.
