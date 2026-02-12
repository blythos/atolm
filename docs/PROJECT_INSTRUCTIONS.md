# Project: Panzer Dragoon Saga Decompilation & Saturn RE Tools

## Overview

This project is a full decompilation and modern reimplementation of the Sega Saturn game Panzer Dragoon Saga (1998, Team Andromeda), with the broader goal of developing reusable tools for decompiling Saturn games in general. The end goal is a native modern port: an application that loads the original disc image and runs the complete game on modern hardware — not emulation, but a true reimplementation.

The user has a Disc 1 ISO available as a raw binary track image. The working approach has three reinforcing tracks: asset extraction (understanding and parsing all data formats), code decompilation (converting SH-2 machine code to readable C/C++), and reimplementation (building a modern engine that runs the decompiled logic with the original assets). Asset extraction is the validation layer for decompilation — every format we crack proves our understanding of the code that processes it.

See PROJECT_SCOPE.md for the full architecture, phase breakdown, and development order.

## Key Reference: yaz0r's Azel Project

The primary reference for understanding PDS internals is yaz0r's open-source C++ decompilation at github.com/yaz0r/Azel (MIT licence, 468 commits, 2015-2020, open-sourced February 2026). This is a partial functional reimplementation of the PDS game engine. We use it as a **specification reference** — reading the C++ to understand binary formats — but write our own Python tools rather than depending on the C++ code directly.

Key source paths in the Azel project:
- `AzelLib/processModel.h/cpp` — 3D model parsing, quad format, pointer patching
- `AzelLib/dragonData.cpp` — Dragon filename tables, loading sequences
- `AzelLib/field/` — Field area loading, file lists
- `AzelLib/3dEngine_textureCache.cpp` — VDP1 VRAM and texture management
- `AzelLib/kernel/fileBundle.h` — MCB bundle structure, VDP1 offset storage
- `AzelLib/common.h` — s_MCB_CGB struct, dragon config tables

## Architecture: Sega Saturn Basics

- **CPU**: Dual Hitachi SH-2 (32-bit RISC, big-endian)
- **VDP1**: Sprite/polygon processor — handles all 3D geometry as textured quads
- **VDP2**: Background/tilemap processor — 2D backgrounds, scroll planes
- **VDP1 VRAM**: 512KB at 0x25C00000–0x25C7FFFF — texture pixel data lives here
- **VDP2 Color RAM**: Palette data used by both VDP1 (bank mode) and VDP2
- **All data is big-endian**

## File Formats (Established)

### Disc Image
- Raw Mode 2 CD-ROM: 2352 bytes/sector (16 header + 2048 data + 288 ECC)
- Standard ISO9660 filesystem, PVD at sector 16

### MCB (Model/Character Block)
- Self-contained binary bundle loaded to Work RAM
- Starts with a pointer table: N × u32 big-endian offsets to sub-resources
- Sub-resources include: 3D models, hierarchy trees, static pose data, animation data
- Pointer table ends where the first pointed-to data begins

**3D Model sub-resource:**
```
+0x00  s32  radius (bounding sphere, fixed-point 20.12)
+0x04  u32  numVertices
+0x08  u32  verticesOffset (relative to bundle start)
+0x0C  ...  quads[] (variable length, terminated by all-zero indices)
```

**Vertex format:** 3 × s16 big-endian, fixed-point 12.4 (divide raw value by 16 for float)

**Quad format (20 bytes + lighting data):**
```
+0x00  u16[4]  vertex indices (A, B, C, D)
+0x08  u16     lightingControl (bits 8-9: mode 0-3)
+0x0A  u16     CMDCTRL (bits 4-5: texture flip H/V)
+0x0C  u16     CMDPMOD (bits 3-5: color mode, bit 6: SPD transparency)
+0x0E  u16     CMDCOLR (palette/LUT address)
+0x10  u16     CMDSRCA (texture source address)
+0x12  u16     CMDSIZE (bits 8-13: width÷8, bits 0-7: height)
```

Lighting modes append extra data after each quad:
- Mode 0: +0 bytes (plain)
- Mode 1: +8 bytes (single normal)
- Mode 2: +48 bytes (per-vertex normal + color)
- Mode 3: +24 bytes (per-vertex normal)

**Hierarchy node (12 bytes):**
```
+0x00  u32  modelOffset (or 0)
+0x04  u32  childOffset (or 0)
+0x08  u32  siblingOffset (or 0)
```

**Static pose data (36 bytes per bone):**
```
+0x00  s32[3]  translation XYZ (16.16 fixed-point)
+0x0C  s32[3]  rotation XYZ (16.16, where 0x10000 = 360°)
+0x18  s32[3]  scale XYZ (16.16, rest pose = 0x10000)
```

### CGB (Character Graphics Block)
- Raw texture pixel data loaded directly to VDP1 VRAM
- No header — just pixels
- Paired 1:1 with MCB files by filename (DRAGON0.MCB → DRAGON0.CGB)

### Texture Addressing (Critical Discovery)
The raw CMDSRCA value in the MCB × 8 gives the byte offset directly into the CGB file. This has been verified across **all** asset types (dragons, characters, NPCs, enemies, bosses, field geometry). The VDP1 offset patching (`vdp1Pointer`) and VRAM base address cancel exactly: `(CMDSRCA + offset) × 8 - VRAMbase = CMDSRCA × 8`. Similarly, for LUT mode palettes: `CMDCOLR × 8` = byte offset into CGB.

### Texture Color Modes
- **Mode 0** (4bpp bank): Palette index = CMDCOLR | nibble. Needs VDP2 Color RAM (PNB files) — currently rendered as greyscale.
- **Mode 1** (4bpp LUT): 16-color palette stored in CGB at CMDCOLR×8. **Fully working.**
- **Mode 4** (8bpp bank): 256-color palette via CMDCOLR×2. Needs VDP2 Color RAM.
- **Mode 5** (16bpp direct): RGB555 (ABGR1555 with bit 15 = MSB flag). **Fully working.**

Saturn RGB555: R = bits 0-4, G = bits 5-9, B = bits 10-14, MSB = bit 15.

### SCB (Screen/Background Block)
VDP2 background tilemap data. Used for menus, 2D screens. Not yet parsed.

### PNB (Palette Block)
VDP2 Color RAM data. Contains palette tables needed by bank-mode textures. Not yet parsed.

### Other Formats
- `.PRG` — SH-2 executable overlays (scene scripts, field logic)
- `.PCM` — Audio samples
- `.CPK` — Cinepak FMV video
- `.SEQ` — Sequenced music/sound
- `.FNT` — Font data
- `.BIN` — Various binary data
- `.EXB` — Extended binary data

## Auto-Discovery Heuristics (Proven Working)

The MCB pointer table entries can be classified without game code knowledge:

1. **Models**: entry where +0x04 is a small count (1-5000) and +0x08 is a valid offset with room for count×6 bytes of vertex data
2. **Hierarchies**: entry where all three u32 values are either 0 or valid offsets, and the first value (if non-zero) points to model-like data
3. **Static pose data**: entry with N×36 byte blocks where all scale fields ≈ 0x10000 (1.0 in 16.16 fixed-point). Search by matching bone count from hierarchy.
4. **Animation data**: entries after pose data, typically 3-4KB each, with flags/numBones/numFrames header structure

## Disc 1 Asset Survey

Total on disc: 360 MCB files, 370 CGB files, 163 SCB, 162 PNB, 89 BIN, 59 PRG, 14 CPK, 270 PCM.

351 MCB/CGB pairs matched by filename. Naming conventions:
- `DRAGON0-7` — 8 dragon base forms (Basic Wing through Solo Wing)
- `DRAGONM1-7` — Dragon morph intermediate models
- `DRAGONC0-7` — Dragon combat-specific models  
- `C_DRA0-7` — Dragon collision meshes (MCB only, no CGB)
- `RIDER0` — Edge riding pose (MCB only)
- `FLD_*` — Field exploration geometry (65 pairs, largest assets on disc)
- `*MP` / `*MP0-8` — Map/environment models (towns, interiors)
- `X_A_*`, `X_E_*`, `X_F_*`, `X_G_*` — NPC models (Seekers' Stronghold variants)
- `Z_A_*`, `Z_B_*`, `Z_E_*`, `Z_F_*` — NPC models (Zoah variants)
- `EDGE`, `AZEL` — Main character battle models
- Named enemies: `BEMOS`, `GRIGORIG`, `BARIOH`, `RAHAB`, `ANTIDRAG`, etc.
- `BATTLE` — Battle system common assets
- `COMMON3` — Shared/common 3D assets
- `WORLDMAP` — World map model

## Skeletal Transform Pipeline

To produce a correctly posed model:
1. Parse the hierarchy tree (count bones via recursive walk)
2. Find the matching pose data (N×36 bytes where all scales ≈ 1.0)
3. Walk the tree using the engine's exact traversal: for each node, push matrix → translate → rotateZYX → draw model → recurse children → pop → continue siblings
4. Rotation order is ZYX (Z applied first, then Y, then X)
5. Coordinate space: vertex raw s16 × 16 → 16.16 fixed-point. Bone translations already in 16.16. Output: divide all by 4096 for reasonable OBJ scale.
6. Saturn angles: 0x10000 = full circle (360°). Convert: radians = raw_s32 / 65536 × 2π

## Current Tool Status

### Working
- ISO9660 filesystem reader (reads raw track images)
- MCB pointer table parser with auto-classification
- 3D model vertex/quad extraction
- Hierarchy tree walker with skeletal transforms
- Pose data finder (heuristic scale-field matching)
- Texture decoder: LUT mode (4bpp mode 1) and direct RGB (16bpp mode 5)
- Textured OBJ+MTL+PNG export pipeline
- Software renderer for visual verification

### Not Yet Implemented
- Bank-mode texture palettes (modes 0, 4) — needs PNB parser
- SCB (2D background) parser
- PNB (palette) parser
- Animation keyframe decoder
- Multi-hierarchy scene assembly (field maps need scene placement data from PRG files)
- Batch extraction tool with disc browser UI
- Export to formats beyond OBJ (glTF would preserve skeletal data)

## Known Edge Cases

- **AZELMP and similar *MP files**: These are map/environment bundles with many standalone models and no hierarchy. The individual models are placed by scene scripts in PRG files, not by skeletal transforms. Currently extracted as unassembled parts at origin.
- **Multi-hierarchy MCBs** (e.g. GRIGORIG with 20 hierarchies, BEMOS with 7): Contain multiple model configurations — different phases, attack states, or sub-assemblies. The first hierarchy is typically the main/default form. All hierarchies share the same pose data pool.
- **MCBs without CGBs** (C_DRA1-7, MDLCHG, RIDER0): Collision meshes or pose-only data — no textures needed.
- **CGBs without MCBs** (MENU, SAVE, TUTORIAL, etc.): 2D screen assets using SCB/PNB system instead of 3D models.

## Broader Saturn RE Goals

While PDS is the primary target, the tool architecture should keep generality in mind:
- The ISO9660 reader works for any Saturn disc
- VDP1 quad format and texture modes are Saturn-wide, not PDS-specific
- The MCB bundle structure may be Team Andromeda-specific, but the principles (pointer table → sub-resources) are common across Saturn games
- Fixed-point arithmetic conventions (12.4, 16.16, 20.12) are standard Saturn/SH-2 patterns
- Other Saturn games using similar structures: Panzer Dragoon, Panzer Dragoon Zwei, Burning Rangers (all Team Andromeda)
