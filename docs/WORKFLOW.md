# Per-function matching workflow (Bucket 3, deliverable 2)

The industrial loop for taking one 1ST_READ.PRG function from "address in
the inventory" to "matched or attempted with findings". This document
formalizes and **supersedes the interim per-function effort bound in
charter §3** (formal adoption pending the STOP 3 charter amendment).
Ritual owner (charter §3 document-ownership rule): effort-protocol
revisions land here at Bucket 3+ checkpoints.

Everything below assumes the charter is read: matched = byte-identical,
proof values are tool-generated only, no Sega bytes in the repo.

## The loop

```
select candidate → read original (Ghidra/objdump) → draft C → shape →
tools/try_match.sh → MATCH: land it | bound hit: classify residual, land
attempted + findings | residual outside known families: STOP, escalate
```

### 1. Candidate selection
From `config/targets/1ST_READ.functions.tsv` (+ segment map):
- state of the covering segment is `unattempted` (never library-*,
  never the pocket, never data);
- evidence includes `prologue` (or `entry`) — detector-confirmed starts;
- prefer functions whose span (start → next inventory start) is fully
  instruction-covered; note callers count — 0-caller functions may be
  dead code or mis-seeded (fine to match, worth a note).
Campaign-style selection states its criteria up front and must be
representative — no cherry-picking easy wins to flatter the match rate.

### 2. Reading the original
- `python3 tools/segment_report.py <vma>` — evidence chain first.
- Disassembly (local only, never committed): the tools-local Ghidra
  project (`tools/ghidra_gen.sh`), or
  `tools/sh-elf.sh <dir> objdump -D -b binary -m sh2 -EB orig.bin`
  after extracting the span with try_match (it writes
  `build/try/<vma>/orig.bin` on every run).
- Boundary gotchas (FINDINGS §Gotchas, binding): function starts come
  from prologues, not "previous rts" (multi-return functions mis-split
  otherwise); trailing literal pools disassemble as fake instructions —
  eyeball the end; the span-to-next default may include inter-function
  pad (`--size` to trim).

### 3. Drafting and shaping C
- Unit = the function plus its literal pool (`SEGALOGO` precedent: a
  unit owns its pools). Draft at `src/1ST_READ/func_<vma>.c` (K&R style,
  see `func_06006622.c`).
- Self-containment: elfcnv rejects unresolved externals — callees must
  be stubbed *in the same file, in binary order* (SHC resolves near
  calls to direct `bsr` from same-file ordering) or the call shaped as
  a pool-loaded `jsr` where that is what the original does.
- Shape iteration order (cheapest first): local variable count/order and
  `register` usage; expression temp structure (chained vs separate
  assignments, nested vs temped call args); typed temp variants;
  pointer-vs-index access shapes; declaration order. The Bucket 0.5/1
  findings files show worked examples of shapes that flip each idiom.

### 4. Compile + byte-diff: one command
```
tools/try_match.sh <vma> [--size N] [--src FILE] [--flags "..."]
```
extract → compile (canonical shc-5.0-r31, `-optimize=1 -speed -macsave=0`, in the
container) → cmp/sha256 → on MATCH prints the manifest record with
tool-generated proof values; on NON-MATCH prints differing-byte count,
first divergence, relocation-hole annotation (from the SYSROF object via
`tools/sysrof.py --holes` — those offsets are link-time values, not
codegen differences), and the instruction-level diff.

**Differ choice (deliverable 2 decision): asm-differ, not objdiff.**
Reasons: asm-differ has a native `sh2` arch (the sotn-decomp Saturn
lineage — our toolchain recipe already descends from theirs); it consumes
objdump text, which our container already produces, so adapting it is a
wrapper (`tools/fndiff.sh`: raw-blob→ELF conversion, container-delegating
objdump bridge, pip-free shims); objdiff would need to parse an object
format it doesn't know (SYSROF) or trust elfcnv's mislabeled ELF output,
plus a Rust toolchain. The clone is pinned in gitignored `tools-local/`.

### 5. Effort protocol (formal; supersedes charter §3 interim bound)
- **Leaf functions: 5 source shapes or 1 focused hour**, whichever first.
- **Functions with calls or branches: 8 shapes or 2 hours.**
- A "shape" = a structurally distinct source variant honestly aimed at
  the residual (renaming a variable is not a shape).
- On hitting the bound: classify the residual against the known idiom
  families below, then land as `attempted` with a findings file. Never
  relax the match criterion; never grind past the bound — drift-class
  residuals are expected until a mid-1997 SHC surfaces (charter §4).

**Known idiom families** (residual classification vocabulary; evidence in
FINDINGS.md, FINDINGS_0.6b, docs/FINDINGS/SEGALOGO_segalogo.md):
1. `addressing-mode` — single-use out-of-range offset: `mov #imm,r0` +
   `@(r0,Rn)` (original) vs pointer-increment shape (R31).
2. `constant-materialization` — immediate chaining / derive-by-`add`
   from a live register (original) vs literal-pool load (R31); includes
   the `add #2` peephole and its pool-padding knock-on.
3. `schedule-permutation` — same instructions, permuted order
   (epilogue/entry schedules).
4. `register-numbering` — temp register allocation differs, call
   machinery exact.
5. `mask-test` — `mov #m,Rt; and Rt,Rn; cmp/eq Rt,Rn` (original) vs
   `and #m,r0; cmp/eq #m,r0` (R31).

**A residual OUTSIDE these families is not filed — it is escalated**
(see below). It might be a new drift family (worth documenting properly),
a wrong function boundary, or a wrong compiler hypothesis for that code.

### 6. Landing
- **MATCH:** commit the source; paste try_match's manifest record into
  `config/targets/1ST_READ.yaml` `functions:`/`units:` verbatim (values
  are tool-generated — hand-typing any hash is fabrication per charter
  §5); split the segment row via the same tool-emitted hashes; run
  `python3 tools/check.py` green before claiming anything.
- **ATTEMPTED:** findings file at `docs/FINDINGS/1ST_READ_<vma>.md`
  (template: what matched structurally, the residual clusters, family
  classification, shapes tried, flag sweeps if any — prose only, no byte
  dumps); manifest status `attempted` + `findings:` path (schema-enforced).
- Either way the five/six-state split is what gets reported — never the
  matched number alone.

## Escalation & model tiering

**Escalation cases — pause and present for human review regardless of
which model is running the loop:**
1. A residual outside the known idiom families (§5).
2. Ambiguity in success criteria (span/boundary genuinely unclear,
   "which bytes am I matching" has no tool-derivable answer).
3. Anything touching the charter or the manifest schema.

**Model tiering:** this loop is deliberately runnable by cheaper models —
the procedure is written down, the verdict is an objective byte-diff, the
effort bound is mechanical, and the filing format is structured. Judgment
calls are concentrated in the escalation list above, which routes to the
human. Campaign-style sessions may be launched with `--model sonnet` at
the human's discretion; the escalation rules are what make that safe.

## Verification reminders
- `make check` / `tools/check.py` is the only green that counts.
- Every claim in a findings file must be re-runnable (the try_match
  invocation is the reproduction recipe; record `--size`/`--flags` used).
- try_match writes everything to gitignored `build/try/<vma>/` — no
  Sega bytes can leak into the repo from this loop; the CI tripwire
  backstops.
