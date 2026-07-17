# atolm

A **verified, byte-matching decompilation** of *Panzer Dragoon Saga*
(Sega Saturn, 1998, US disc set, product MK-81307).

Correctness means one thing here: our C source, compiled with the
original-era toolchain, produces bytes identical to the original binaries
(`cmp`/sha256 proof). The only progress metric this repo recognizes is
matched code.

## What this is / is not

**Is:** C source, splitter/build configs, containerized period toolchain,
sha256 manifests, documentation.

**Is not:** a playable reimplementation, an asset viewer/extractor, or a
ROM host. There are **zero Sega-derived bytes in this repository** — no
disc images, no extracted binaries, no disassembly listings, no hex dumps.
You supply your own legally obtained disc; everything derived from it
lives in gitignored paths (`ISOs/`, `extracted/`, `build/`) and never
enters version control. CI enforces this with a tripwire on every push.
Asset tooling and modern-reimplementation work are explicitly out of
scope (see the sibling pds-asset-tools project for the former).

## Toolchain

Hitachi **SH SERIES C/C++ Compiler Ver. 5.0 (Release31)** under Wine,
flags `-optimize=1 -speed`, plus sh-elf binutils — identified as PDS's
compiler family by empirical fingerprinting (see
[docs/ATTRIBUTION_AND_FINDINGS.md](docs/ATTRIBUTION_AND_FINDINGS.md)).
The compiler is proprietary and is **not** in this repo: `make setup`
fetches it from a pinned, sha256-verified public archive into a
gitignored directory. A secondary Cygnus GNU 2.7-96Q3 container exists
for a suspected middleware pocket.

Known caveat: Release31 is a Nov-1998 build, likely one generation newer
than the compiler Team Andromeda used (no 2.x–4.x binary is known to
survive). Some functions need C reshaped to match, and a small class of
scheduling/peephole differences may be unmatchable until an era-correct
build surfaces; these are documented per-function in `docs/FINDINGS/`,
never papered over.

## Building with your own disc

Prerequisites: Linux with Docker, GNU make, python3 + PyYAML.

```
make setup      # build toolchain containers, fetch + verify the compiler
# put your Panzer Dragoon Saga (USA) Disc 1 bin/cue in ISOs/
make extract    # pull target PRGs from the disc (refuses wrong dumps)
make            # compile matched units, splice the rest, assemble PRGs
make check      # byte-identity vs your extracted originals
```

`make check-functions` re-proves every matched unit from committed C
without needing a disc (hash equality with the manifest is the proof) —
this is what CI runs.

## Current status (Bucket 1)

| target | rebuild | matched code |
|---|---|---|
| SEGALOGO.PRG (3620 bytes) | byte-identical via placeholder splice | 0/328 code bytes matched; best candidate at 317/328 (96.6%), residual documented in [docs/FINDINGS/SEGALOGO_segalogo.md](docs/FINDINGS/SEGALOGO_segalogo.md) |
| 1ST_READ.PRG | proofs-only (no rebuild planned this bucket) | 1 function matched with sha256 proof |

A unit only counts as **matched** when its recompiled bytes are
byte-identical; "96.6% of bytes equal" is honestly reported as
*attempted*, and the build splices original bytes from your disc until
the match lands.

## Attribution

This project stands on the decompilation community's methods and the
preservation community's archives. See
[docs/ATTRIBUTION_AND_FINDINGS.md](docs/ATTRIBUTION_AND_FINDINGS.md) for
what is original here versus inherited, and for the full resource list.
