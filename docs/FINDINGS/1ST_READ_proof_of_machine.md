# 1ST_READ.PRG — proof-of-machine: one translation unit, byte-diffed

**Date:** 2026-07-20
**Deliverable:** Bucket 4 STOP 1, deliverable 2 (+ the STOP-1 GO/NO-GO).
**Unit:** 0x06026f3c .. 0x06026f86 (74 bytes), three functions.
**Source:** `src/1ST_READ/unit_06026f3c.c` (status: attempted).

## The unit and how it was detected

`tools/tu_cluster.py` closes a seed under the **undirected** `bsr` relation
(if X calls Y with an in-range PC-relative `bsr`, both are in the unit —
callers *and* callees) plus shared literal-pool-run membership. The smallest
closed, internal-`bsr`, non-library unit is:

- `cksum` (0x06026f3c, 28 B, leaf) — weighted checksum over a record body
  (skips the 4-byte header), weight = 1-based position index;
- `store_cksum` (0x06026f58, 22 B) — `*p = cksum(p, n)`; and
- `verify_cksum` (0x06026f6e, 24 B) — `*p == cksum(p, n)`.

Both wrappers `bsr` into the shared leaf. The unit has **no literal pool and no
external calls**, so the only translation-unit properties under test are the
two intra-unit `bsr` displacements and SHC's instruction schedule — the
cleanest possible isolation of the TU-bounding question. (`cksum` is called
from six sites across ~1.3 KB, i.e. it has external linkage; only the three
co-located functions are needed to reproduce this 74-byte span.)

## Byte-diff verdict (the GO/NO-GO is decided here, not by judgment)

`tools/try_match.sh 0x6026f3c --size 74 --src src/1ST_READ/unit_06026f3c.c
--flags "-optimize=1 -speed -macsave=0"`:

| function | bytes | differing | verdict |
|---|---|---|---|
| `cksum` | [0x00,0x1c) 28 | 14 | drift |
| `store_cksum` | [0x1c,0x32) 22 | **0** | **BYTE-IDENTICAL** |
| `verify_cksum` | [0x32,0x4a) 24 | 10 | drift |
| **unit** | **74** | **24** | non-match |

**The full unit is not byte-identical → per the STOP-1 rule, STOP HARD and
report as a strategy decision.** But the substrate is strongly positive:

- **TU membership detection is correct.**
- **Both intra-unit `bsr` displacements reproduce byte-exactly** — the unit
  compiles to the **exact 74-byte size**, and the `bsr` instructions match.
- **One complete function (`store_cksum`) is byte-identical** *within the
  co-compiled unit* — proof that co-compilation is the right unit and that
  byte-identity is reachable this way.
- **Every residual is a known drift family** (§ idiom families): `cksum` is
  register-numbering (#4: SHC assigns `sum`→r7/`w`→r6 where PDS used r6/r7)
  plus schedule (#3: which of `w++`/`sum+=` fills the `bf.s` delay slot);
  `verify_cksum` is schedule (#3: SHC fills the `bsr` delay slot with a
  register move where PDS emitted `nop`) plus register (#4).

The register-numbering residual in `cksum` was probed with 7+ source shapes
(operand order, declaration order, `register` hints, increment-first loop) —
`b4` recovered the exact delay-slot schedule but **no shape flips the
`sum`/`w` register pair.** This is textbook #4 drift: unshapeable from C,
exactly the search space `decomp-permuter` explores. It reinforces the STOP-3
permuter recommendation, now demonstrated at the translation-unit level.

## New toolchain finding — `Macsave=0` recovers PDS's MAC calling convention

While diffing `cksum`, R31 emitted a `sts.l macl,@-r15` / `lds.l @r15+,macl`
pair around **every** function that uses `mul.l` (confirmed on a trivial
`return a*b;`). The original `cksum` uses `mul.l` and does **not** preserve
MACL. SHC R31 exposes `Macsave=[0|1]` ("Selects MACL/MACH register save
rules"); the default under `-optimize=1 -speed` is save-on-clobber, but PDS's
compiler treated MACL/MACH as **caller-saved**. With `-macsave=0`:

- the spurious 4-byte save/restore disappears;
- `store_cksum` becomes byte-identical;
- functions with no `mul`/`mac` are unaffected (the option only gates the
  save), so it cannot regress the existing match (0x06014608 has no multiply).

This is the same 1996-vs-1998 version-drift boundary seen from Bucket 0, now
pinned to a specific, flag-controlled mechanism. **Recommendation: add
`-macsave=0` to the canonical invocation** — staged for human decision in
`docs/CHARTER_AMENDMENTS_BUCKET4.md` (charter §0 owns the toolchain recipe;
not self-applied). Without it, the entire class of multiply/MAC functions
carries a fixed +4-byte residual that is *not* codegen drift but a
calling-convention mismatch.

## What this means for Bucket 4 (the strategy decision for the human)

The machine — boundary detector → TU membership detection → co-compile →
byte-diff — **works**: it bounds units correctly and reaches byte-identity
(one function proven, size and cross-function `bsr` exact). It does **not**
reach whole-unit byte-identity under R31 alone, because per-function #3/#4
drift is pervasive and, as measured, unshapeable. The two levers that convert
"structurally correct, drift-near-miss" into exact matches are (a) the
`-macsave=0` calibration (free, recommended now) and (b) the scoped permuter
for #3/#4 (recommended at STOP 3, now with unit-level evidence). This is a
strategy input, not a decision the byte-diff makes for us.

## Reproduce / spot-check

```
python3 tools/tu_cluster.py 0x6026f3c
tools/try_match.sh 0x6026f3c --size 74 --src src/1ST_READ/unit_06026f3c.c \
    --flags "-optimize=1 -speed -macsave=0"
```
`store_cksum`'s byte-identity is checkable in the per-function table above from
`build/try/0x06026f3c/{orig,unit}.bin` (both gitignored, disc-derived).
