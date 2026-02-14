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
