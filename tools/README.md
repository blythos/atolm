# Tools

This directory contains various tools for working with Panzer Dragoon Saga asset formats.

## Structure

- `cpk_extract.py`: Extracts audio (WAV) and video (MP4) from Sega FILM CPK files.
- `common/`: Shared modules for Saturn formats and disc reading.
    - `iso9660.py`: ISO9660 disc image reader.
    - `saturn.py`: Shared Saturn hardware utilities (endianness, color decoding, etc.).

## Usage

### CPK Extractor

Extracts CPK files from a disc image:
```bash
python tools/cpk_extract.py --disc path/to/game.iso
```

Batch process all ISOs in a folder:
```bash
python tools/cpk_extract.py --batch-folder path/to/isos/ --output output/videos/
```

Individual CPK file:
```bash
python tools/cpk_extract.py --cpk path/to/movie.cpk
```

### Batch FMV Processor

Automated tool to extract, subtitle, and mux FMVs from game discs.

**Usage:**

Process a single disc (CUE or BIN):
```bash
# Using a CUE file (recommended for multi-bin games)
python tools/batch_process_FMVs.py "path/to/game.cue"

# Using a BIN file directly
python tools/batch_process_FMVs.py "path/to/track1.bin"
```

Batch process a folder of disc images:
```bash
# Scans for .cue files (or .bin files if no cues found)
python tools/batch_process_FMVs.py "path/to/isos_folder/"
```

**Output:**
Files are organized into `Disc_X` subdirectories (e.g. `Disc_1/`, `Disc_2/`) automatically.
You can specify a custom output directory:
```bash
python tools/batch_process_FMVs.py "path/to/isos/" --output "my_output_folder/"
```

## Model Extractor and Viewer

```bash
# 1. Extract all models from a disc
python3 pds_extract.py "Disc1_Track1.bin" --extract-all -o models/

# 2. Serve the viewer
cd models/
cp ../pds_viewer.html index.html
python3 -m http.server 8080

# 3. Open http://localhost:8080
```

## Extractor: `pds_extract.py`

Reads a raw Mode 2 CD-ROM track image and extracts all MCB/CGB model pairs.

**Three files per model — no proprietary data in the tool itself:**
- `{NAME}_model.json` — Geometry (vertices, quads, hierarchy, poses, texture atlas mapping)
- `{NAME}_anim.json` — Animation data (raw track data for the viewer's state machine)
- `{NAME}_tex.png` — Texture atlas PNG with all decoded textures

Plus a `manifest.json` listing all extracted models with categories.

### Commands

```bash
# List all models on disc
python3 pds_extract.py disc.bin --list

# Extract one model
python3 pds_extract.py disc.bin --extract DRAGON0 -o output/

# Extract everything
python3 pds_extract.py disc.bin --extract-all -o output/ -v
```

### Output Format

**Vertices** are raw s16 values in Saturn 12.4 fixed-point format. Divide by 16.0 for world units.

**Bone translations** are raw s32 values in 16.16 fixed-point. Divide by 65536.0 for the same world units.

**Bone rotations** are raw s32 values in 16.16 fixed-point. The integer part (value >> 16) masked to 12 bits gives a Saturn angle (0-4095 = 0°-360°). Convert: `radians = (raw >> 16 & 0xFFF) × 2π / 4096`.

**Quads** preserve the original VDP1 command data: vertex indices, lighting mode, colour mode, texture flip flags, CMDSRCA/CMDCOLR/CMDPMOD/CMDSIZE.

**Animations** store raw track data using yaz0r's RLE format. The viewer simulates the exact state machine from `AzelLib/kernel/animation.cpp`.

## Viewer: `pds_viewer.html`

The viewer consists of `pds_viewer.html`, `viewer_renderer.js`, and `viewer_animation.js`.

### Usage

**1. Portable Mode (Recommended)**
Copy all three viewer files into the output directory containing your extracted models (where `manifest.json` is).
```bash
cp tools/pds_viewer.html tools/viewer_renderer.js tools/viewer_animation.js output/
cd output/
python3 -m http.server
# Open http://localhost:8000/pds_viewer.html
```

**2. Development Mode**
Run the server from the project root. The viewer in `tools/` will automatically look for models in `output/raw/`.
```bash
python3 -m http.server
# Open http://localhost:8000/tools/pds_viewer.html
```

**Features:**
- **Categorised Asset Browser**: Dragons, Characters, NPCs, Fields, Maps, Objects, Overworld.
- **Advanced Rendering**: Textured quad rendering with all Saturn colour modes (LUT, RGB555, bank greyscale fallback).
- **Inspection Tools**:
  - **Grid**: 3D floor grid for scale reference.
  - **BBox**: Per-bone bounding box wireframes.
  - **Labels**: Bone index overlay for mapping hierarchy to geometry.
  - **Atlas**: Full-screen texture sheet viewer.
  - **Hex Offsets**: Hexadecimal file offsets for all assets in the Info Panel.
- **Animation Playback**: Faithful replication of the Saturn animation state machine.

### Animation System

The viewer's animation engine is a **direct port of the original Saturn logic**, reverse-engineered by **yaz0r** (from the Azel decompilation project). This ensures 1:1 accuracy with the game's movement:

- **Mode 0**: Direct per-frame values.
- **Mode 1**: Accumulated values with variable-length encoding.
- **Mode 2/3**: Spline interpolation (used for camera paths).
- **Mode 4**: Keyframes every 2 frames with half-step linear interpolation.
- **Mode 5**: Keyframes every 4 frames with quarter-step interpolation.

The custom `stepAnimationTrack` logic handles the Saturn's specific RLE-like compressed track format, where values encode both a delay (low 4 bits) and a delta (high 12 bits).

## Sequential Music Extraction

PDS uses Sega's CyberSound system: `.SEQ` files contain note event sequences (similar to MIDI); `.BIN` files paired with them contain the PCM instrument samples (CyberSound TON format). The EPISODE/INTER `.SND` files are archives containing multiple SEQ and TON banks.

### Step 1: Extract SEQ and BIN files from the disc

```bash
python tools/seq_extract.py \
  --iso "ISOs/Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin" \
  --extract \
  --output output/seq_extract/
```

This extracts all standalone `.SEQ` and `.BIN` files into `output/seq_extract/raw/` and writes a `catalog.json` mapping tracks to names (sourced from the disc's hidden SNDTEST.PRG).

To just list what's available without extracting:
```bash
python tools/seq_extract.py --iso "ISOs/..." --scan
```

### Step 2: Convert a SEQ file to MIDI

```bash
python tools/seq_to_midi.py \
  --input output/seq_extract/raw/KOGATA.SEQ \
  --output output/midi/KOGATA.mid
```

The resulting `.mid` file can be opened in any DAW or MIDI player.

### Step 3: Extract instrument samples from a BIN tone bank

```bash
python tools/ton_to_wav.py \
  --input output/seq_extract/raw/KOGATA.BIN \
  --output output/ton_wav/KOGATA/
```

Each extracted WAV file contains one unique instrument sample from the bank. Files are named `sample_NNN_at0xOFFSET_Xbit_22050hz.wav`.

**Notes:**
- Multiple voices in a bank often share the same underlying PCM region; the tool deduplicates automatically.
- Some BIN files (e.g. `BOS5BGM.BIN`) are part of SND bundle packages and will have fewer extractable samples than voices — this is expected. The remaining samples live in a companion TON bank within the SND archive.
- Sample rate defaults to 22050 Hz. If an instrument sounds pitched wrong, the true rate is one of: 7680, 11025, 15360, 22050, or 44100 Hz. The BIN file does not encode this directly.
- 8-bit samples are signed Saturn PCM converted to unsigned WAV automatically.
- 16-bit samples are big-endian on Saturn, byte-swapped to little-endian WAV automatically.

### SND bundle archives (EPISODE1–4, INTER12/23/35)

These require manual splitting at documented byte offsets before the TON and SEQ banks inside them can be processed. Offsets for the USA Disc 1 builds are in `docs/antigravity-tasks/TASK_SEQ_EXTRACTOR.md`.

## Font Extraction

PDS uses VDP2 bitmap fonts stored in `.FNT` files — 16×16 1bpp glyph bitmaps. **All FNT glyphs are Japanese kanji/kana** — no Latin/Roman characters exist in this format. English text visible in FMV cutscenes is rendered via a separate system (likely VDP1 sprites or baked into CPK video frames).

```bash
# List all FNT files on disc
python tools/fnt_extract.py --iso "path/to/disc1.bin" --scan

# Extract all fonts + built-in kernel font from COMMON.DAT
python tools/fnt_extract.py --iso "path/to/disc1.bin" --all --kernel --output output/fonts/

# Extract a specific font
python tools/fnt_extract.py --iso "path/to/disc1.bin" --name MENU.FNT --output output/fonts/

# Also export individual glyph PNGs
python tools/fnt_extract.py --iso "path/to/disc1.bin" --all --individual --output output/fonts/

# From a pre-extracted raw file
python tools/fnt_extract.py --input raw/MENU.FNT --output output/fonts/
```

**Output per font:**
- `{NAME}_font.png` — sprite sheet (16 columns, white-on-transparent)
- `{NAME}_font.json` — metadata (glyph count, font type, grid dimensions)
- Optional: `{NAME}/glyph_NNN.png` — individual glyphs (with `--individual`)

**FNT categories on Disc 1 (65 files):**

| Prefix | Count | Content |
|--------|-------|---------|
| FLD_*  | 13    | Field area UI (NPC/location names) |
| BTL_*  | 26    | Battle encounter text |
| EVT*   | 18    | Event/cutscene/town dialogue |
| System | 4     | MENU, ITEM, SAVE, SHOP |
| Other  | 4     | MENUEN, MENUBK, WORLDMAP, FLAGEDIT |

## Known Limitations

- **Bank-mode textures** (colour modes 0 and 4) render as greyscale. These need VDP2 Color RAM data from PNB files, which requires parsing scene-specific PRG bytecode.
- **Field geometry** (FLD_* files) contains many standalone models placed by PRG scripts. They extract as unassembled parts at origin.
- **Gouraud shading** data (per-vertex normals and colours from lighting modes 1-3) is extracted but not yet fully rendered — the Saturn's Gouraud system modulates texture colours in ways that need further research.

## Requirements

- Python 3.6+ (no dependencies — pure stdlib)
- A modern browser with WebGL support
- Any HTTP server (Python's built-in `http.server` works fine)

## Debug Tools

Located in `tools/debug/`. Run these from the project root.

-   `inspect_iso.py`: Lists all files on a disc image, including hidden/nested files.
    ```bash
    python tools/debug/inspect_iso.py
    ```
-   `audit_fmv_durations.py`: Checks for subtitle/video duration mismatches in the output folder.
    ```bash
    python tools/debug/audit_fmv_durations.py
    ```
-   `compare_discs.py`: Compares MOVIE.DAT and MOVIE.PRG checksums across all discs.
-   `inspect_movie_dat.py`: Dumps the raw contents of MOVIE.DAT from a disc.
-   `inspect_movie_prg.py`: Dumps the raw contents of MOVIE.PRG from a disc.
