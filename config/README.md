# config/ — manifest and splitter formats

All files here are hand-edited YAML, read by `tools/` scripts and CI. They
contain **only our own analysis and sha256 hashes** — never Sega-derived
bytes (no hex dumps, no disassembly, no data segments).

## compilers.yaml

Canonical compiler definitions keyed by id (`shc-5.0-r31`,
`cygnus-2.7-96Q3`): description, container image, provenance hashes of the
fetched toolchain, environment, and the invocation template. A function
record's `compiler` + `flags` against this file fully reproduces its build.

## targets/<NAME>.yaml — one per PRG target

Top-level keys:

| key        | meaning                                                        |
|------------|----------------------------------------------------------------|
| `target`   | output filename, e.g. `SEGALOGO.PRG`                           |
| `role`     | `build` (full byte-identical rebuild) or `proofs-only`         |
| `disc`     | disc number the file lives on                                  |
| `disc_path`| ISO9660 path, consumed by `make extract` via `tools/iso9660.py`|
| `size`     | expected byte size of the extracted file                       |
| `sha256`   | hash of the extracted file — `make extract` refuses a mismatch |
| `vma_base` | load address (from IP.BIN or overlay header — disc-authoritative) |
| `segments` | ordered five-state segment map covering the whole file        |
| `units`    | compilation-unit records — the buildable/provable entities     |
| `functions`| per-function progress records within units                     |

### `segments` (the segment map)

Ordered, non-overlapping, and must cover `[0, size)` exactly — the build
concatenates them and `make check` compares the result to the extracted
original. For `role: build` targets the map drives the build; for
analysis-mapped targets (1ST_READ) it is the committed segmentation record.
Every segment carries a `state`, one of exactly five values
(Bucket 2 vocabulary):

| state | meaning | build source |
|---|---|---|
| `matched` | unit recompiles byte-identical, sha256-proven | compiler output, hash-verified |
| `attempted` | honest non-match, drift-class residual, **analysis on file** in docs/FINDINGS/ | original bytes (spliced) |
| `unattempted` | code no one has tried to match yet | original bytes (spliced) |
| `library-candidate` | code suspected SGL/SBL/CPK library (heuristic — Bucket 3 confirms or demotes) | original bytes (spliced) |
| `data` | not code; lives on the disc forever | original bytes (spliced) |

```yaml
segments:
  - {start: 0x0,   end: 0x120, state: matched, unit: foo}
  - {start: 0x120, end: 0x200, state: data}
  - {start: 0x200, end: 0x300, state: unattempted}
  - {start: 0x300, end: 0x400, state: library-candidate}  # + evidence: prose
```

Consistency rules, machine-enforced by every tool (`validate_manifest` in
`tools/prg.py`):

- `matched` / `attempted` segments must name a `unit:` whose `status`
  **agrees with the segment state** — disagreement fails the build/check,
  so the two can never drift apart silently.
- An `attempted` unit must carry a `findings:` path that exists —
  "attempted" without a residual-diff analysis on file is not a state
  this schema can express.
- `library-candidate` segments should carry an `evidence:` note (prose:
  version-string proximity, call-graph position, idiom style). Certainty
  is not required; confirmation or demotion is Bucket 3 work.

Only `matched` segments ever receive compiler output. Everything else is
the placeholder mechanism: bytes copied at build time from the
locally-extracted original, never committed.

**Reporting rule:** every progress line any tool prints, and every README
stats block, shows the full five-state split. The matched figure is never
presented alone.

### `units` (the hash manifest — byte-proof entities)

Compilers emit literal pools that can be shared across functions in one
translation unit (seen in SEGALOGO.PRG: one merged pool serves both
functions), so the smallest independently provable byte span is the unit's
whole `.text`, not a single function. One record per compilation unit:

```yaml
units:
  segalogo:
    source: src/SEGALOGO/SEGALOGO.c
    size: 0x148              # .text byte length incl. literal pools
    status: attempted        # unattempted | attempted | matched
    findings: docs/FINDINGS/SEGALOGO_segalogo.md  # required when attempted
    compiler: shc-5.0-r31    # key into compilers.yaml
    flags: [-optimize=1, -speed]
    sha256: b7e93583...      # hash of the original bytes this unit must hit
    matched: 2026-07-16      # date, once status: matched
```

The match proof is: compiling `source` with `compiler` + `flags` and
extracting `.text` yields `size` bytes whose sha256 equals `sha256`. CI
re-verifies this for every `matched` record **without any disc content** —
the hash equality itself is the proof. A single-function unit (like the
1ST_READ proofs, which use per-function records with the same fields) is
just the degenerate case.

`attempted` documents an honest non-match per the failure protocol; the
residual-diff analysis lives at the `findings:` path (docs/FINDINGS/,
prose only, never byte dumps) and the field is mandatory — validation
fails without it. `unattempted` means not yet attempted.

### `functions` (progress records)

One record per function, for progress accounting and documentation:
`name` (placeholder naming: `func_<vma>`), `vma`, `size`, `unit` (key into
`units`), `status` (same vocabulary as units), optional `notes` describing
observed behavior in prose.
