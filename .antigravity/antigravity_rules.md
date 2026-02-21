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
- Vertices are **s16 fixed-point 12.4** (divide by 16 for float)
- Bone translations/scales are **s32 fixed-point 16.16** (divide by 65536 for float)
- **Viewer coordinate convention**: vertices `/16`, bone translations `/256` (NOT `/65536`) — this preserves correct proportions matching the engine's internal 16.16 space
- Saturn angles: **0x10000 = full circle** (360°). Convert: `radians = raw / 65536.0 * 2π`
- Rotation order is **ZYX** (Z applied first, then Y, then X)
- Texture address: **`CMDSRCA_raw × 8`** = byte offset directly into CGB file (verified across all asset types — no per-file VDP1 offset needed)
- Palette address: **`CMDCOLR_raw × 8`** = byte offset into CGB for LUT mode
- Saturn audio is **signed 16-bit big-endian PCM** — must byte-swap to little-endian for WAV output
- CPK audio sample rate is **32000 Hz** (the FDSC header sample rate field is unreliable — do not use it)
- CPK audio/video chunk discrimination requires a content-aware heuristic: if first 4 bytes of chunk (with first byte masked) equal the chunk size → video interframe; otherwise → audio PCM
- CPK stereo audio is non-interleaved per chunk (first half = left, second half = right)
- FDSC byte 20 is video bpp (24), NOT audio compression. Audio compression is byte 23 (0 = PCM for PDS)
- Saturn RGB555 format: **R = bits 0-4, G = bits 5-9, B = bits 10-14, MSB = bit 15**
- MCB files start with a pointer table of u32 offsets to sub-resources
- Quad terminator: all four vertex indices are zero
- Lighting mode (bits 8-9 of lightingControl) determines extra bytes after each quad: mode 0 = +0, mode 1 = +8, mode 2 = +48, mode 3 = +24
- **Do not modify** MCB/CGB parsing, texture decoding, skeletal transforms, or animation math without coordinating with the project lead. These have been carefully verified.

## Key Reference

This project builds on **yaz0r's Azel project** (github.com/yaz0r/Azel, MIT licence, 76,000+ lines of partial C++ decompilation). Use it as a specification reference for understanding game internals.

Key source paths:
- `AzelLib/processModel.h/cpp` — 3D model parsing, quad format, pointer patching
- `AzelLib/kernel/animation.cpp` — Animation track stepping, bone transform accumulation (stepAnimationTrack)
- `AzelLib/town/townScript.cpp` — PRG bytecode interpreter (subtitle opcodes)
- `AzelLib/kernel/fileBundle.h` — MCB bundle structure

## Coding Standards

- **Python tools** (`tools/` directory): Python 3.8+, use type hints, docstrings on public functions, no external dependencies beyond Pillow and NumPy
- **Binary parsing**: Always use `struct.unpack('>...')` for big-endian. Document every offset. Use named constants, not magic numbers.
- **Commit messages**: Prefix with subsystem — `[asset]`, `[decomp]`, `[engine]`, `[docs]`, `[tools]`, `[fix]`
- **Testing**: If you modify a tool that was previously working, verify it still produces correct output before committing. Do not "fix" things that aren't broken.

## Constraints

- **Never commit game data** — no disc images, extracted assets, or ROM dumps
- **Never copy code from emulators** unless they use a compatible licence
- The disc image is the ROM — the reimplementation loads original disc data at runtime; users provide their own copy
- When in doubt about a binary format, check yaz0r's Azel source first

## Disc Image Location

The disc images are in the `ISOs/` directory (gitignored, never commit). Disc 1 files:
- `ISOs/Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin` — main data track (ISO9660 filesystem + all game files)
- `ISOs/Panzer Dragoon Saga (USA) (Disc 1) (Track 2).bin` — audio track (CD-DA, not for extraction)
- `ISOs/Panzer Dragoon Saga (USA) (Disc 1) (Track 3).bin` — audio track (CD-DA, not for extraction)
- `ISOs/Panzer Dragoon Saga (USA) (Disc 1).cue` — cue sheet

Always use Track 1 for file extraction.

## What Needs Doing

Check `docs/PROGRESS.md` for the full current status. The immediate open tasks are:

1. **Fix `tools/ton_to_wav.py`** — First pass exists but produces broken output. TON files are Saturn sound sample banks (BIN paired with SEQ). Research the format and fix.
2. **PNB parser** (palette data) — Unblocks bank-mode textures (modes 0 and 4). These currently render as greyscale.
3. **PCM audio extraction** — 270 `.PCM` files on disc. Unknown whether they have headers or are raw PCM. Investigate and build `tools/pcm_extract.py`.
4. **SCB parser** (2D background tilemap data) — VDP2 tilemap format, needed for menu backgrounds and 2D screens.
