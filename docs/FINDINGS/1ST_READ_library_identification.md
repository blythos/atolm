# 1ST_READ.PRG — SBL/SGL/CPK library identification (Bucket 3, STOP 1)

**Date:** 2026-07-18
**Method:** fingerprint scan of every code section of every module in the
0.6b Sept-1997 SDTK catalogue (SBL 6.21 / SGL 3.20; 26 .LIBs + 6 SYS_*.OBJ
= 238 modules, 232 scannable) against the locally extracted 1ST_READ.PRG.
Relocation holes and never-emitted filler bytes are wildcards; every other
byte must match at a unique placement. No Sega/CRI bytes committed — library
files live in gitignored `reference/SBL621/`; this document and the
committed artifacts carry only names, offsets, and our hashes.

## Tooling (committed, re-runnable)

- `tools/sysrof.py` — native Hitachi SYSROF .LIB/.OBJ reader (sections,
  object data, relocation holes, exported symbols). Format derived
  empirically from SYSDUMP.EXE output (the SDTK's own period tool, run
  under dosemu in 0.6b) paired with raw bytes. **Validated byte-exact
  against all 58 P-sections sysdump extracted in 0.6b (58/58), plus the
  independent sha256 anchor `cb4cb5b7…` for dma_cpu0 recorded in
  FINDINGS_0.6b.**
- `tools/coffar.py` — ar + SH-COFF reader for the catalogue's GNU-built
  .A variants (used for the pocket check).
- `tools/libscan.py` — the scanner; `--emit tsv|yaml|symbols` produced,
  respectively, `config/targets/1ST_READ.libscan.tsv` (full result record,
  including misses — negative results are findings), the manifest segment
  rows, and the symbols-file rows. All hashes tool-generated (charter §5).

Reproduce: `python3 tools/libscan.py extracted/1ST_READ.PRG
reference/SBL621/LIB/*.LIB reference/SBL621/LIB/SYS_*.OBJ --emit tsv`
Spot-check any address: `python3 tools/segment_report.py <vma>`.

## Results

**15 exact hits (14 unique placements — gfsd_buf/gfs_buf are byte-identical
twins), 5,056 bytes promoted to `library-identified`, 60 API symbols entered
as `verified`.** All placements are unique (no multi-hits), mutually
contiguous within three regions, and the largest region ends exactly at the
data-segment boundary 0x3cd20 — strong structural corroboration.

| lib | modules scanned | hit | bytes |
|---|---|---|---|
| SEGADGFS/SEGA_GFS | 19 | 1 (twin) | 168 |
| SEGA_CDC | 17 | 4 | 1,640 |
| SEGA_CPK | 15 | 6 | 2,620 |
| SEGA_DMA | 8 | 3 | 624 |
| all others (incl. SGL 62, SCL 36, PCM 16…) | 173 | 0 | 0 |
| **total** | **232** | **15** | **5,052** (+4 link pad) |

Identified members and placements (file offsets; vma = +0x06006000):

- `0x377f0` gfs(d)_buf — GFBF_* buffer API
- `0x3a6c0` cdc_dev, `0x3a764` cdc_sel, `0x3a998` cdc_bif, `0x3ab9c`
  cdc_bio — contiguous CDC block (CDC_* API)
- `0x3c070` cpk_deb, `0x3c14c` slavesh, `0x3c278` cpk_scu, `0x3c35c`
  dma_cpu0, `0x3c4e4` dma_cpu3, `0x3c574` dma_cpu5, `0x3c5cc` cpk_ra,
  `0x3c7f0` cpk_er, `0x3ca4c` cpk_mc — contiguous CPK/DMA block ending
  exactly at the data segment (Cinepak decoders, slave-SH dispatcher,
  SCU-DSP DMA, CPU DMA)

## Why the hit rate is what it is (the version-drift story, confirmed again)

PDS ships **1996-vintage** SBL (version strings in the binary: BUP 1.21,
GFS_SBL 2.10, SYS 2.20, CPK 1.24 1996-06-14); the catalogue is
**Sept-1997** (SBL 6.21). Exact hits are therefore the members that did not
change between those releases: all four hits with **zero** C-compiler
involvement beyond stable leaf code, and notably the A_SH **assembly**
members (cpk_ra/cpk_er/cpk_mc/cpk_scu, 2,100 bytes), which are immune to
compiler codegen drift. This is the same 1996-vs-1997 drift boundary the
0.6b compiler work established from the other side.

The two interior gaps between hit clusters ([0x37898,0x3a6c0) 11,816 bytes
and [0x3ad28,0x3c070) 4,936 bytes) are flanked by exact placements and
expected to hold the 1996-build members the 1997 fingerprints missed; they
are marked `library-candidate` with that evidence, per the never-force rule.

## Negative results (logged with equal rigor)

- **The ascending-order pocket** (0x1c820–0x1c97c, GCC-idiom, CRI/CPK
  hypothesis): NO match in the catalogue — neither the SHC .LIBs nor the
  GNU .A archives; 8-gram similarity against every catalogue code section
  is noise-level (max 7/290). Consistent with PDS's older CPK 1.24; the
  middleware hypothesis stands unconfirmed.
- **SEGALOGO.PRG:** both attempted units scanned against the full
  catalogue — no hits. They are game code, not library members; their
  attempted (drift-class) status is unchanged.
- **SGL (62 modules), SCL (36), PCM, MPG, MTH, MEM, STM, SYS…:** zero
  exact hits. For SGL this is expected — PDS uses its own renderer; no
  SGL version string appears in 1ST_READ's version block either.
- The two version-string function clusters (0x33692, 0x3450c) did not hit
  (version-reporting code differs across releases by definition); they
  remain `library-candidate`.

## Negative spot-check of the scanner itself (checkpoint addition)

Requested at STOP 1 review: prove the scanner distinguishes near-miss from
hit rather than only finding what it sought. `cdc_cmn` (C member, scan
status miss, 760 fixed bytes) was exhaustively aligned against every
2-aligned offset of 1ST_READ.PRG: **best partial alignment 657/760
(86.4%) at 0x30c8c — refused** (hit threshold is 100% of fixed bytes).
Positive control `cdc_dev` returns exactly its recorded placement at
100.0%. The 86.4% peak is itself informative: drift-class divergence at a
plausible placement for the *1996-build* cdc_cmn, in an unattempted
region below the marked gaps — recorded here as near-hit evidence for
future work, not claimed (never-force rule).

## Schema note (for checkpoint review)

This bucket adds the sixth segment state **`library-identified`**
(bytes proven to be a named catalogue member; requires `member:`;
enforced in `tools/prg.py`) per the Bucket 3 brief. It is identification,
not decompilation: such segments never enter the match loop and subtract
from the denominator of code left to match. config/README.md updated.
