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
