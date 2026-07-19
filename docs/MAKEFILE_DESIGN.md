# Build system design (Bucket 1, step 1 checkpoint — not yet implemented)

Design for review before implementation (step 3). Success criterion it must
satisfy: clean clone → `make setup` → user drops disc in `ISOs/` →
`make extract` → `make` → `make check` GREEN, `SEGALOGO.PRG` byte-identical,
reproducible — with zero Sega-derived bytes in the repo.

## Targets

| target                | needs disc | what it does |
|-----------------------|------------|--------------|
| `make setup`          | no         | builds both Docker images (`atolm-shc`, `atolm-cygnus`); runs `toolchain/fetch-shc.sh` (downloads or reuses the pinned sega-saturn-sdks archive, sha256-verified, into gitignored `toolchain/vendor/shc/`) |
| `make extract`        | yes        | for each `config/targets/*.yaml`: pulls `disc_path` from `ISOs/` via `tools/iso9660.py` into `extracted/`, then **refuses to proceed** unless size and sha256 match the manifest (wrong disc / bad dump caught here) |
| `make` (all)          | yes        | for each `role: build` target: compiles every `status: matched` function in its container, hash-verifies each against its manifest record, then assembles `build/<TARGET>` from the segment map (compiled bytes for `matched` segments, bytes spliced from `extracted/<TARGET>` for every other state — see config/README.md for the segment-state vocabulary, adopted Bucket 2, six states since Bucket 3) |
| `make check`          | yes        | `cmp` + `sha256sum` of `build/<TARGET>` vs `extracted/<TARGET>`; prints per-target PASS/FAIL and per-function match stats; GREEN only on byte-identity |
| `make check-functions`| **no**     | CI-safe subset: recompiles every `matched` function from committed C and compares the compiled `.text` sha256 to the manifest hash. Hash equality proves the match without any disc content |
| `make tripwire`       | no         | scans the committed tree (git ls-files) and fails on any binary content: banned extensions, NUL bytes, files matching known Sega-derived hashes |
| `make clean`          | no         | removes `build/` only (never touches `ISOs/`, `extracted/`, `toolchain/vendor/`) |

## Data flow

```
ISOs/*.bin|cue ──extract──▶ extracted/SEGALOGO.PRG   (gitignored, hash-gated)
                                    │
src/SEGALOGO/*.c ──shc container──▶ build/obj/*.bin  (per-function .text bytes)
                                    │  ▲ each hash-verified vs manifest
                                    ▼  │
config/targets/SEGALOGO.yaml ──assemble (segment map)──▶ build/SEGALOGO.PRG
                                    │
                              make check: cmp vs extracted/SEGALOGO.PRG
```

## Placeholder mechanism (criterion 3)

The segment map in each `build`-role manifest is ordered and covers
`[0, size)` exactly. The assembler script (`tools/build_target.py`) walks it:

- `matched` segments: bytes come from compiled objects. Each unit is
  compiled in the SHC container via its recorded invocation; the `.text`
  bytes are extracted with `sh-elf-objcopy` and sha256-checked against the
  unit record **before** splicing. A hash mismatch aborts the build —
  a unit that stops matching can never silently ship inside a "green"
  PRG.
- all other states (`attempted` / `unattempted` / `library-candidate` /
  `data`): bytes are copied from `extracted/<TARGET>` at the same offsets,
  at build time, locally. Nothing derived from them is ever written inside
  the repo tree (`build/` is gitignored).

Progress metric falls out of the manifest: the full six-state byte split
(matched is never reported alone).

## Where verification happens

- **Locally (with disc):** full-PRG byte-identity (`make check`) — the only
  place it can happen, since data segments live on the disc.
- **CI (no disc):** `make setup` (images build), committed C compiles,
  `make check-functions` (per-function hash proofs), `make tripwire`.

## Implementation notes

- Orchestration: plain GNU Make at the top; per-step logic in small Python
  scripts under `tools/` (host python3 + PyYAML, both present; no ninja, no
  generators — the scale doesn't justify them yet).
- Compilation happens with 8.3 uppercase filenames in a scratch dir under
  `build/` (SHC is a '90s toolchain; don't feed it long paths), copied from
  `src/` by the build script. `src/` layout stays readable.
- Containers run as the invoking uid (`toolchain/shc/run.sh`) so `build/`
  is never root-owned.
- The tripwire is a `tools/tripwire.sh` run by CI on every push and
  available locally; it checks `git ls-files` content, not the working
  tree, so gitignored disc data doesn't false-positive.

## Open decisions for review

1. **SHC vendor mount vs. bake-in:** chosen: fetch to gitignored
   `toolchain/vendor/shc/` and bind-mount read-only at `/opt/shc`. Keeps
   the 229MB proprietary archive out of image layers, lets a local copy be
   reused (`SHC_ARCHIVE=` override), and the image itself stays
   redistributable. Cygnus stays baked-in (small, public, pinned URL) —
   mirrors the proven sotn-decomp recipe.
2. **Manifest granularity:** one YAML per PRG target (`config/targets/`),
   compilers factored into `config/compilers.yaml`. Segment map and
   function records live together in the target file since they must stay
   in sync.
3. **1ST_READ.PRG** is `role: proofs-only`: `make extract` pulls and
   verifies it (needed so `check-functions` proofs trace to a real file),
   but it is never built or `make check`-ed in Bucket 1.
