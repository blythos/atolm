# Session Log

## Session 1: Project Planning
**Scope:** Discussed RE methodology for Saturn games. Established the approach: extract disc image → identify file formats → build parsers → export to modern formats. Identified key constraints (no Saturn emulator in the tool environment, working from raw binary data). Decided to start with Disc 1.

## Session 2: Disc Extraction & Filesystem Analysis
**Scope:** Uploaded Disc 1 ISO (616MB, raw Mode 2 track image). Built ISO9660 parser, extracted all 1,847 files. Identified file types by extension: MCB/CGB (3D model+texture pairs), SCB/PNB (2D backgrounds+palettes), PRG (SH-2 executables), CPK (Cinepak video), PCM (audio), SEQ (music), FNT (fonts), BIN/DAT (data).

**Key finding:** The disc has a flat directory structure (no subdirectories). All 1,847 files are in the root.

## Session 3: Executable Analysis & Community Research
**Scope:** Analysed 1ST_READ.PRG (253KB main executable). Found SDK version 6.10, identified SH-2 instruction patterns. Discovered debug menu activation addresses. Reviewed yaz0r's Azel decompilation project on GitHub (468 commits, MIT licence, C++ reimplementation of PDS engine). Established Azel as our primary format reference.

**Key finding:** yaz0r's code contains complete parsers for MCB/CGB formats, making format reverse engineering vastly easier.

## Session 4: File Format Documentation
**Scope:** Deep analysis of yaz0r's source code to document MCB, CGB, SCB, PNB formats. Traced the full asset loading pipeline: MCB→Work RAM, CGB→VDP1 VRAM, pointer patching, texture addressing. Documented VDP1 quad format, vertex format, hierarchy system, color modes.

**Output:** PDS_File_Formats_Analysis.md

## Session 5: MCB-to-OBJ Extractor
**Scope:** Built the first extraction tool (pds_mcb_to_obj.py, 21,610 bytes). Implemented pointer table parsing, model extraction, quad parsing with all 4 lighting modes, hierarchy walking, OBJ export. Extracted all 8 dragon forms, Edge, Azel, and FLD_A3 field geometry.

**Issue discovered:** All exported models appeared as collapsed lumps — skeletal parts dumped at local origin without bone transforms.

## Session 6: Skeletal Transform Debugging
**Scope:** Found static pose data at pointer table entries [65] and [66] (31 bones × 36 bytes each). Implemented proper hierarchy traversal matching yaz0r's `modeDrawFunction10Sub1` exactly. Resolved coordinate space mismatch between 12.4 vertex format and 16.16 bone format. Applied ZYX rotation order.

**Key finding:** The engine converts 12.4 → 16.16 via ×16 multiplication. Unified both spaces by working in 16.16 then dividing by 4096 for output.

**Output:** All 8 dragon forms exported with correct poses (DRAGON0-7_posed.obj), visual verification renders.

## Session 7: Texture Extraction & Cross-Asset Validation (Current)
**Scope:** Built CGB texture decoder for 4bpp LUT and 16bpp RGB modes. Implemented textured OBJ+MTL+PNG export. Discovered and verified that CMDSRCA×8 directly indexes into CGB with no per-file offset needed.

Tested pipeline across all asset categories: dragon, player character (Edge), characters (Azel battle + NPC variants), enemy (Bemos), boss (Grig Orig), field geometry (Excavation Site). **Zero failures** — all 8 test cases had 0 out-of-range texture addresses.

**Outputs:** Textured model zips for DRAGON0, EDGE, AZEL, X_A_AZ, Z_A_EG, BEMOS, GRIGORIG, FLD_A3_0. Comparison render grid. Individual multi-angle renders.

**Key findings:**
- 351 MCB/CGB pairs on Disc 1, systematically named by category
- Bank-mode textures (mode 0) need PNB files for palettes (currently greyscale)
- Map/environment files (*MP) have standalone models without hierarchies — need scene script data from PRG files to assemble
- Multi-hierarchy MCBs (bosses, complex enemies) contain multiple model configurations
- The auto-discovery pipeline (classify → find hierarchy → find pose → walk → export) works reliably across all tested asset types

Discussed tool architecture: ISO reader built-in, disc browser for asset selection, auto-discovery pipeline for extraction.

**Generated project files** for Claude project setup.
