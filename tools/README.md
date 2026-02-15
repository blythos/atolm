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

A single HTML file using Three.js. Place it alongside the extracted JSON/PNG files and serve via any HTTP server.

**Features:**
- Categorised asset browser (Dragons, Characters, NPCs, Fields, Maps, Other)
- Textured quad rendering with all Saturn colour modes (LUT, RGB555, bank greyscale fallback)
- Skeletal hierarchy with correct transforms
- Animation playback with frame scrubbing
- Orbit camera (left-drag rotate, right-drag pan, scroll zoom)

### Animation System

The viewer's animation engine is a faithful port of yaz0r's Azel decompilation:

- **Mode 0**: Direct per-frame values from track arrays
- **Mode 1**: `stepAnimationTrack` with per-frame accumulation  
- **Mode 4**: Every-2-frame keyframes with half-step interpolation
- **Mode 5**: Every-4-frame keyframes with quarter-step interpolation

The `stepAnimationTrack` function implements the Saturn's RLE-like track format:
track values encode both a delay (low 4 bits) and a value (high 12 bits, sign-extended).

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
