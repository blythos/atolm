# atolm — Panzer Dragoon Saga matching decompilation

## Goal statement (verify all work against this)
A verified, byte-matching decompilation of Panzer Dragoon Saga (Sega Saturn,
1998, US disc set, product MK-81307). Correctness means: compiles to bytes
identical to the original binaries. The only progress metric this repo
recognizes is matched code. Modern reimplementation, asset tooling, and
viewers are explicitly out of scope and live elsewhere.

## Canonical toolchain (Bucket 0 verdict, 2026-07)
Hitachi SHC 5.0 (Release31) under Wine, flags -optimize=1 -speed, plus
sh-elf binutils. Known caveat: Release31 is a Nov-1998 Dreamcast-devkit
build, likely one generation newer than PDS's true compiler (2.x–4.x, no
surviving binary found). Consequence: some functions need C reshaped to
match; two known recurring idiom gaps (addressing-mode choice, constant
materialization) are bounded per-function work, NOT grounds to relax the
match standard. Standing watch: if any SHC 2.x–4.x binary surfaces,
re-run the Bucket 0.5 four-candidate battery before adopting it.
Secondary toolchain: Cygnus GCC 2.7-96Q3 under dosemu (for the suspected
GCC-family middleware pocket; also SN ccsh = Cygnus 2.7-97r1a rebadge).

## Definition of success (never redefine)
A function is matched when its recompiled bytes are identical to the
original (cmp/sha256 proof). "Behaves the same" or "close" is not a match.
A PRG target is complete when make check rebuilds it byte-identical
locally from the user's own disc.

## Legal rules (absolute)
- ZERO Sega-derived bytes in the repo: no disc images, no extracted PRGs,
  no disassembly listings of game code, no data segments, no hex dumps.
- The repo contains: our C source, splitter/build configs, our tools and
  containers, documentation, and sha256 hashes of expected outputs.
- The user supplies their own disc; extraction happens locally into
  gitignored paths only.
- CI must include a tripwire that fails if binary/disc-derived content is
  committed.

## Verification discipline
- Before any multi-step change, state what will be run and what output
  proves success. Never mark complete without showing that output.
- Every match records: function address, size, exact compiler invocation,
  and its byte-proof (hash), reproducibly.
- CI verifies per-function hash matches and build integrity; full-PRG
  verification is local-only (make check) because data segments live on
  the disc.

## Layout
- ISOs/          gitignored; user's disc images (read-only inputs)
- extracted/     gitignored; PRGs and segments pulled from the disc
- src/           our C source (committed)
- config/        splitter configs, symbol maps, expected-hash manifests
- toolchain/     Dockerfiles and scripts for SHC/Wine and Cygnus/dosemu
- tools/         our Python/shell tooling (iso9660.py vendored here)
- docs/          documentation incl. ATTRIBUTION_AND_FINDINGS.md
- build/         gitignored; all build output
- tools-local/   gitignored; Ghidra install + generated projects (disc-derived)
- reference/     gitignored; reference clones (yaz0r/Azel, Ymir) — naming/
                 format evidence ONLY, never imported as source

## Task routing (two-agent rule)
Claude Code in WSL: anything touching src/, config/, toolchain/, builds,
matching, or any claim of "matches". Antigravity on Windows: documentation
drafting and Windows-verifiable tooling only. An agent may only do work it
can verify where it stands.

## Scope bans (drift guards)
- NO asset extraction/conversion of any kind (models, textures, audio,
  video). That work lives in the sibling repo (pds-asset-tools).
- NO reimplementation code, renderers, SDL, viewers.
- asm-differ landed in Bucket 3 (tools/fndiff.sh, adapted to our
  SHC/container output; the clone is gitignored in tools-local/). The
  PERMUTER decision made at STOP 3: decomp-permuter NOT adopted (the
  #3/#4 residuals are translation-unit-context-driven or version-blocked,
  not source-permutable). The scale-out unit is TU-ordered reconstruction
  (tools/tu_cluster.py + tools/tu_build.py); any context/position-aware
  permuter is deferred behind a measured cost trigger. NO
  dedup/similarity-clustering infrastructure yet (decide at Bucket 5). Ghidra entered at Bucket 2 as LOCAL-ONLY
  tooling: the generated project is disc-derived and lives in gitignored
  tools-local/; only the generator script, seeds detector, and symbols
  file are committed.
- NO second MATCHING target until SEGALOGO.PRG is complete and
  checkpointed. Analysis and infrastructure work on other files (1ST_READ
  mapping, library identification, per-function calibration proofs) is
  permitted; only full match campaigns to a completed target are gated.
- If a task presents as "make X generic for other games" rather than
  "match X", it is out of scope (deferred: Saturn Decomp Kit).

## Checkpoint protocol
Work proceeds in buckets with STOP points. STOP means: present results,
end turn. The human reviews externally before continuing. Failure protocol:
persistent non-match after honest iteration is documented in
docs/FINDINGS (with residual diff analysis), never papered over.
Every bucket close and every STOP that lands a new finding includes an
attribution check: does docs/ATTRIBUTION_AND_FINDINGS.md reflect all
findings closed since its last revision? If not, refreshing it is part
of the checkpoint, not deferred work.
