# Atolm — Panzer Dragoon Saga Decompilation

## Project Context

You are working on a full decompilation and modern reimplementation of Panzer Dragoon Saga (Sega Saturn, 1998, Team Andromeda). The end goal is a native modern port that loads the original disc image and runs the complete game on modern hardware.

Before starting any task, read these project documents for context:
- `docs/PROJECT_SCOPE.md` — Full architecture, phase breakdown, development order
- `docs/PROJECT_INSTRUCTIONS.md` — Detailed format specifications, asset pipeline, established knowledge
- `docs/TECHNICAL_REFERENCE.md` — Binary format byte layouts, fixed-point arithmetic, VDP1/VDP2 details
- `docs/PROGRESS.md` — Current status, what's done, what's next
- `docs/QUICK_REFERENCE.md` — Code snippets for common operations

## Critical Technical Facts

These have been verified against real game data. Do not deviate from them.

- All data is **big-endian** (SH-2 native byte order)
- Vertices are **s16 fixed-point 12.4** (divide by 16 for float, or multiply by 16 then divide by 4096 to match bone space)
- Bone translations/scales are **s32 fixed-point 16.16** (divide by 65536 for float)
- Saturn angles: **0x10000 = full circle** (360°). Convert: `radians = raw / 65536.0 * 2π`
- Rotation order is **ZYX** (Z applied first, then Y, then X)
- Texture address: **`CMDSRCA_raw × 8`** = byte offset directly into CGB file (verified across all asset types — no per-file VDP1 offset needed)
- Palette address: **`CMDCOLR_raw × 8`** = byte offset into CGB for LUT mode
- Saturn RGB555 format: **R = bits 0-4, G = bits 5-9, B = bits 10-14, MSB = bit 15**
- MCB files start with a pointer table of u32 offsets to sub-resources
- Quad terminator: all four vertex indices are zero
- Lighting mode (bits 8-9 of lightingControl) determines extra bytes after each quad: mode 0 = +0, mode 1 = +8, mode 2 = +48, mode 3 = +24

## Key Reference

This project builds on **yaz0r's Azel project** (github.com/yaz0r/Azel, MIT licence, 76,000+ lines of partial C++ decompilation). Use it as a specification reference for understanding game internals.

## Coding Standards

- **Python tools** (`tools/` directory): Python 3.8+, use type hints, docstrings on public functions, no external dependencies beyond Pillow and NumPy
- **C++ reimplementation** (`src/` directory, future): Follow yaz0r's Azel coding conventions for consistency
- **Binary parsing**: Always use `struct.unpack('>...')` for big-endian. Document every offset. Use named constants, not magic numbers.
- **Commit messages**: Prefix with subsystem — `[asset]`, `[decomp]`, `[engine]`, `[docs]`, `[tools]`

## Constraints

- **Never commit game data** — no disc images, extracted assets, or ROM dumps
- **Never copy code from emulators** unless they use a compatible licence
- The disc image is the ROM — the reimplementation loads original disc data at runtime, users provide their own copy
- When modifying the asset extraction pipeline (MCB/CGB parsing, texture decoding, skeletal transforms), verify changes against known-good output before committing

## Disc Image Location

The disc images are in the `ISOs/` directory (gitignored, never commit). Disc 1 files:
- `ISOs/Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin` — main data track (this is the one containing the ISO9660 filesystem and all game files)
- `ISOs/Panzer Dragoon Saga (USA) (Disc 1) (Track 2).bin` — audio track
- `ISOs/Panzer Dragoon Saga (USA) (Disc 1) (Track 3).bin` — audio track
- `ISOs/Panzer Dragoon Saga (USA) (Disc 1).cue` — cue sheet

Always use Track 1 for file extraction. Tracks 2 and 3 are CD-DA (Red Book) audio tracks.

## What Needs Doing

Check `docs/PROGRESS.md` for the current phase and open tasks. The project follows a strict dependency order — earlier phases must be complete before later ones can begin. The immediate priorities are:

1. PNB parser (palette data) — unblocks bank-mode textures
2. SCB parser (2D backgrounds)
3. Animation keyframe decoder
4. PCM/SEQ audio extraction
5. CPK video extraction
6. Batch extraction tool with disc browser
