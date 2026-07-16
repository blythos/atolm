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
| `segments` | ordered segment map covering the whole file (`build` role only)|
| `functions`| per-function match records (the hash manifest)                 |

### `segments` (splitter config, `build` role only)

Ordered, non-overlapping, and must cover `[0, size)` exactly — the build
concatenates them and `make check` compares the result to the extracted
original. Each entry:

```yaml
segments:
  - {start: 0x0,   end: 0x120, type: code}          # compiled from src/
  - {start: 0x120, end: 0x200, type: data}          # spliced from extracted/
  - {start: 0x200, end: 0x300, type: code_unmatched} # spliced from extracted/
```

- `code` — covered by matched functions; bytes come from the compiler and
  are hash-verified against the function records.
- `data` / `code_unmatched` — placeholder mechanism: bytes are copied at
  build time from the locally-extracted original (never committed). A
  `code_unmatched` segment is work remaining; `data` stays spliced forever
  (data lives on the disc).

### `functions` (hash manifest)

One record per function we have attempted. Fields:

```yaml
- name: func_06006622        # placeholder naming: func_<vma>
  vma: 0x06006622            # address in the loaded binary
  size: 18                   # byte length of the original function
  status: matched            # matched | attempted
  source: src/1ST_READ/func_06006622.c
  compiler: shc-5.0-r31      # key into compilers.yaml
  flags: [-optimize=1, -speed]
  sha256: 66e77b5a...        # hash of the original function's bytes
  matched: 2026-07-15
  notes: optional free text
```

The match proof is: compiling `source` with `compiler` + `flags` and
extracting `.text` yields `size` bytes whose sha256 equals `sha256`. CI
re-verifies this for every `matched` record **without any disc content** —
the hash equality itself is the proof. `attempted` records document honest
non-matches per the failure protocol; their residual-diff analysis lives in
docs/FINDINGS/, described in prose, never as byte dumps.
