# Panzer Dragoon Saga Decompilation — Findings & Attribution

**Project:** atolm — a byte-matching decompilation of Panzer Dragoon Saga (Sega Saturn, Team Andromeda, 1998)
**Phase covered:** Buckets 0 through 3 STOP 1 (feasibility gate, toolchain verdict, first target, 1ST_READ mapping, library identification), July 2026
**Purpose of this document:** an honest ledger of what this project discovered versus what it inherited. Every finding below is tagged. Nothing here should be read as claiming credit for the decompilation community's methods, tools, or preservation work — this project exists because that groundwork exists.

**Tag legend:**
- **[ORIGINAL]** — a finding or artifact produced by this project that we have not seen documented elsewhere
- **[PRIOR ART]** — an established method, insight, or codebase created by others, which we applied or replicated
- **[COMMUNITY RESOURCE]** — preserved software, archives, or documentation made available by others, without which this work would be impossible

---

## Headline findings

### 1. Panzer Dragoon Saga was compiled with Hitachi SHC — **[ORIGINAL]**
To our knowledge, the compiler used to build PDS has not previously been publicly identified. Empirical comparison of function-prologue codegen conventions against both period toolchains shows the retail binary's dominant code population matches Hitachi SHC (tested: SH SERIES C/C++ Compiler Ver. 5.0 Release31, 1998) and does **not** match Sega's officially distributed Cygnus GCC (cygnus-2.7-96Q3).

**Bucket 0.6 verdict on the exact build:** the "option differences" hypothesis is **falsified** — a sweep of the full documented option space of Release31 (22 flag sets × 3 near-miss candidate functions, sha256-verified) showed the residual codegen differences are hard-coded in this build, not switchable. The version-drift hypothesis, "strongly supported but untestable" at the time of the 0.6 verdict, was subsequently **proven by controlled experiment** (see 1b below). The project adopts SHC 5.0 Release31 with `-optimize=1 -speed` as its canonical toolchain, treats the two recurring idiom gaps (addressing-mode choice, constant materialization) as bounded per-function reshaping work, and maintains a standing watch: if a mid/late-1997 SHC build surfaces, the four-candidate battery gets re-run against it.

### 1a. Sega never distributed the Hitachi compiler — **[ORIGINAL]**
A sweep of every preserved Sega developer disc we could obtain (DTS CDs Nov-95 through Nov-96, SBL 6.01, SGL 3.02, the Sept-1997 Japanese developer toolkit) found the bundled C compiler is always Cygnus GNU plus SN Systems Psy-Q tools; Hitachi SHC appears only as documentation and `.SHC` subcommand files for developers who licensed it separately from Hitachi. SHC was a commercial product sold independently — which is why so few builds survive. The community's sole surviving "Saturn" SHC (saturndev.rar's Hitachi.zip) is byte-identical to the Dreamcast-devkit Release31 build and is labeled as such by its own README. Incidentally, CRI's CPK sample build files use `-OP=1 -SP` (i.e. `-optimize=1 -speed`) — the exact flag pair that produced our byte-identical match — in an older option syntax, consistent with an earlier SHC version having been current during PDS-era development. **Confirmed again in 0.6b:** the Sept-1997 SDTK was fully inventoried (ISO and HFS partitions), ships GNU compilers only, and its own setup docs instruct `SET SHC_LIB` for a *separately installed* compiler — a preservation-history finding: anyone hunting the PDS-era compiler should search Hitachi/embedded-toolchain channels, not Sega disc preservation, which has now been falsified twice as a source.

### 1b. Codegen drift between PDS's compiler and Release31, proven by controlled recompile — **[ORIGINAL]**
The Sept-1997 Sega developer toolkit disc (L21-1000, preserved on the Exodus techdocs DTS mirror) ships SBL libraries whose SYSROF objects carry translator timestamp tags `C_SH9705xx–9708xx` (compiled May–Aug 1997, inside PDS's development window) — **and one library source file, `DMA_CPU0.C`, together with its exact build recipe.** Recompiling that source under Release31 with source and flags held constant yields a different-sized P section (380 bytes vs the 1997 member's 392) with pervasive instruction-selection differences of exactly the near-miss family seen against PDS. Three independent discriminators (single-use offset addressing: 976:73 in PDS, matching the 1997 style; the mask-test idiom: 18:4 in PDS vs Release31's inverted 2:11 on the recompile; and the same-source head-to-head) all side PDS's codegen with the mid-1997 compiler against Release31. This brackets the version hunt to a compiler change made between mid-1997 and the Nov-1998 Release31 build. Full evidence record: FINDINGS_0.6b.

### 1c. An SHC build-dating fingerprint kit — **[ORIGINAL]**
Three practical tests for dating any candidate SHC binary that surfaces, independent of its version banner: (i) **translator tags** — compile any scrap and read the timestamp tag its SYSROF object carries (a PDS-era compiler should emit `C_SH97xxxx`; the target window is `C_SH9705xx–9708xx`); (ii) the **idiom discriminators** from 1b (single-use offset addressing and the mask-test shape); (iii) the **`add #2` constant-derivation peephole and epilogue-schedule** family documented in the SEGALOGO residual analysis (docs/FINDINGS/SEGALOGO_segalogo.md) — the PDS-era compiler derives a neighbouring constant by `add #2` from a still-live register where Release31 loads it from the literal pool, and the entry-epilogue instruction schedule differs in a recognizable 8-byte permutation (same instructions, different order). A candidate build that resolves these residuals on the SEGALOGO unit is the right vintage. This kit is the technical basis of an active public appeal for a mid-1997 SHC build (see the charter's deferred ledger).

### 2. First byte-identical recompilation of shipped PDS code — **[ORIGINAL]**
A function from the retail US Disc 1 `1ST_READ.PRG` (18-byte leaf at 0x06006622), hand-decompiled to C and compiled with SHC 5.0 (`-optimize=1 -speed`), reproduces the shipped bytes exactly (SHA256-verified, zero-diff). This establishes that a verified matching decompilation of PDS is feasible.

### 3. Two-population structure in the binary — **[ORIGINAL finding, using PRIOR ART technique]**
A scripted census of all 354 multi-register function prologues in `1ST_READ.PRG` found 351 following one register-save convention (descending, SHC-style) and an isolated 3-function pocket following the opposite convention (ascending, GCC-style) at 0x06022820–0x0602297c. Hypothesis (unconfirmed): the pocket is statically linked third-party middleware, candidate CRI (a `CPK Version 1.24 1996-06-14` string is present in the binary). Compiler fingerprinting via codegen idiom is an established reverse-engineering technique **[PRIOR ART]**; the systematic census and its application to PDS are ours. *(Bucket 3 update: the pocket matches no member of the Sept-1997 CPK library in either its SHC or its GNU build — the middleware hypothesis stands, still unconfirmed; see docs/FINDINGS/1ST_READ_library_identification.md.)*

### 4. JP/US builds are largely address-identical for resident code — **[ORIGINAL finding]**
Every address-bearing function identifier in yaz0r's Azel repository (script-command dispatch tables, validation-harness hook constants — JP-build addresses) was tested against our independently derived US-build function inventory for 1ST_READ.PRG: **19 of 20 land exactly on US function starts** (the 20th is a documented mid-function return address). Independently corroborated by the load address: the IP.BIN-declared 0x06006000 was confirmed byte-identical across all 253,650 bytes in an emulator savestate fixture. Consequence: Azel's ~700 function names are importable as identification *hypotheses* for the US build with high prior. Derived against **yaz0r's Azel** (github.com/yaz0r/Azel) **[PRIOR ART]** — the addresses and names are his work product; the systematic US cross-validation is ours.

### 5. SBL/CPK library code identified in the shipped binary by object-level fingerprinting — **[ORIGINAL method and finding]**
Bucket 3 STOP 1: every code section of every module in the Sept-1997 SBL/SGL catalogue (238 modules) was fingerprinted — P-section bytes with relocation holes and uncovered filler wildcarded — and searched against 1ST_READ.PRG. Result: **15 exact hits (14 unique placements), 5,056 bytes proven to be named library members, 60 SBL/CPK API symbols placed as verified** (CDC_*, DMA_Cpu*, GFBF_*, CPKD_*, the Cinepak decoders, the slave-SH dispatcher). The hit pattern itself reproduces the version-drift boundary: assembly members (immune to compiler drift) hit; most C members of PDS's older 1996 library releases miss. The identification method and `tools/sysrof.py` (a native reader for Hitachi's SYSROF object format, derived empirically and validated 58/58 byte-exact against period-tool output) are **[ORIGINAL]**; Hitachi's SYSROF format itself and SYSDUMP.EXE, the period dump tool used as the validation anchor, are **[PRIOR ART]**; the SDTK library binaries came via the Exodus techdocs mirror **[COMMUNITY RESOURCE]**. Full record: docs/FINDINGS/1ST_READ_library_identification.md and config/targets/1ST_READ.libscan.tsv (misses included — negative results are findings).

---

## Method and toolchain

### Matching-decompilation methodology — **[PRIOR ART]**
The entire "recompile to byte-identical binaries with the original-era toolchain" discipline was established by the decompilation community (sm64, OoT, and many successors). We adopted it wholesale; we did not invent any of it.

### Saturn-specific matching precedent and toolchain approach — **[PRIOR ART]**
The **sotn-decomp** project (Castlevania: Symphony of the Night, github.com/xeeynamo/sotn-decomp) proved byte-matching decompilation of a commercial Saturn title and published the working recipe: the cygnus-2.7-96Q3 DOS-hosted compiler run under dosemu2 in Docker, paired with modern sh-elf binutils. Our Cygnus container replicates their setup directly. **sozud's saturn-compilers** repository preserves and mirrors the compiler binaries; sozud's saturn-splitter and the wider ecosystem tools (splat, asm-differ, decomp-permuter, decomp.me) define the workflow we intend to follow.

### SHC-under-Wine toolchain and setup gotchas — **[ORIGINAL engineering notes]**
Standing up Hitachi SHC 5.0 under Wine in Docker (`ubuntu:noble` + wine32:i386) and documenting its traps appears not to have been written up before in a decomp context: required environment variables (`SHCPU=SH2`, `SHC_LIB`, `SHC_INC`, `SHC_TMP`) fail with a cryptic `3321 Illegal environment variable` unless given as Windows-style paths **with trailing backslash**; the bundled `elfcnv.exe` SYSROF→ELF converter mislabels output as little-endian (worked around with `sh-elf-objdump -EB`) and rejects objects with unresolved external relocations. Basic SHC/`SHC_LIB` usage was previously documented by RetroReversing's Saturn SDK articles **[PRIOR ART]**, which we built on.

### Corrected 1ST_READ load address for PDS — **[ORIGINAL detail]**
PDS's IP.BIN declares a 1ST_READ load address of **0x06006000** at the 1st-read-address field (offset **0xF0**, ST-040-R4; not the conventional 0x06004000 often assumed for Saturn titles). Product `MK-81307`, master disc date (IP.BIN) `19980318` (the IP.BIN date field — master/gold-disc creation, NOT the NA street date, ~early May 1998). Minor, but anyone disassembling PDS needs it. *(External-audit correction, 2026-07-19: earlier revisions cited offset 0xE8 for the load address; 0xE8 is the master stack pointer, coincidentally equal to the load address for PDS — verified distinct on 12 other Saturn IP.BINs.)*

### Linker relaxation insight — **[PRIOR ART]**
The explanation for direct-`bsr`-vs-indirect-`jsr` call codegen (relevant to one of our near-miss analyses) comes from `RELAX.TXT` by Toshiyasu Morita, shipped inside the period Cygnus toolchain's own documentation.

---

## Resources this project stands on — **[COMMUNITY RESOURCE]**

- **archive.org "Sega Saturn SDKs" collection** — source of the genuine Hitachi SHC toolchain. Uploaded and preserved by community archivists.
- **techdocs.exodusemulator.com** (Sega DTS documentation mirror) — preserved the Sept-1997 Japanese developer toolkit disc (L21-1000) that supplied the drift-proof source file (`DMA_CPU0.C` + build recipe), the translator-tagged SBL/SGL library binaries behind the Bucket 3 identification, and the distribution-history evidence for finding 1a. A load-bearing evidence source for this project.
- **bitsavers.org** — scanned Hitachi SH Series C Compiler manuals (HS0700CLCU4S, 1997), essential for SHC's option system and error codes.
- **antime.kapsi.fi/sega** — long-standing Saturn documentation and file preservation.
- **RetroReversing** (retroreversing.com) — Saturn SDK, Hitachi toolchain, and sample-compilation documentation.
- **dosemu2 / fdpp / comcom32 projects** — make running the DOS-hosted Cygnus compiler on modern Linux possible; prebuilt packages via sozud/dosemu-deb.
- **Wine** — runs the Win32 SHC toolchain on Linux.
- **GNU binutils (sh-elf)** — disassembly and object inspection throughout.

## Related work — **[PRIOR ART]**

- **yaz0r's Azel** (github.com/yaz0r/Azel) — 5+ years and 76,000+ lines of behavioral reimplementation of PDS, MIT-licensed. A different goal from byte-matching (Azel targets functional equivalence in a modern framework), and an enormous reference resource this project expects to consult for function identification and naming hypotheses. Azel's existence and yaz0r's public notes materially informed this project's scoping.
- **Panzer Dragoon community preservation** — Panzer Dragoon Legacy, Will of the Ancients, and decades of community documentation.

---

## Copyright note
This document contains **no Sega-copyrighted material**: no disassembly excerpts, no extracted bytes, no game assets. Findings are described, not reproduced. The project's repositories contain no game data; users must supply their own legally obtained disc images.

## Corrections welcome
If any finding tagged [ORIGINAL] here was in fact published earlier by someone else, we want to know and will re-tag with attribution. The goal is an accurate record, not a claim staked.
