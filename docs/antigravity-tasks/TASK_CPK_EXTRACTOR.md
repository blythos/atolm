# Task: CPK Cinepak Video Extractor

## Objective

Create a Python tool (`tools/cpk_extract.py`) that extracts Cinepak FMV video files from Panzer Dragoon Saga disc images and converts them to a modern video format (MP4 or individual PNG frames + WAV audio).

## Context

PDS Disc 1 contains 14 `.CPK` files — these are Cinepak-encoded full-motion video cutscenes. Cinepak (developed by SuperMatch, used widely in the 1990s) is a well-documented lossy video codec. On the Sega Saturn, CPK files use the "Sega FILM" container format (also called the Sega Cinepak container), which wraps Cinepak video frames and audio samples.

The files on disc are:
- Various cutscene FMVs (intro, ending, story sequences)
- Sizes range from small (a few hundred KB) to large (several MB)

## Sega FILM Container Format

The Saturn uses a specific container around Cinepak data, commonly called "Sega FILM" or just the Saturn CPK format. Key details:

- **Byte order**: Big-endian (same as all Saturn data)
- **Header**: Starts with the ASCII magic `FILM` (0x46494C4D)
- The container has a header chunk, a frame description table (FDSC), and a sample table (STAB)
- Video frames are Cinepak-encoded (codec ID `cvid`)
- Audio is typically raw PCM (signed 16-bit big-endian) or ADPCM

You will need to research the exact Sega FILM container structure. Good references:
- The Multimedia Wiki: https://wiki.multimedia.cx/index.php/Sega_FILM
- FFmpeg source code handles this format (`libavformat/segafilm.c`)
- Various Saturn homebrew documentation

## Requirements

1. **Read CPK files from the disc image** using our ISO9660 reader approach (see `docs/QUICK_REFERENCE.md` for sector reading code)
2. **Parse the Sega FILM container**: Extract the header, frame table, and sample table
3. **Decode Cinepak video frames** to raw RGB pixel data
4. **Extract audio** (PCM or ADPCM) to raw samples
5. **Output options**:
   - Individual PNG frames (simplest, using Pillow)
   - WAV audio file
   - Optionally: MP4 using ffmpeg subprocess call if available
6. **Command-line interface**: `python tools/cpk_extract.py --disc disc1.bin --fileINGS.CPK --output output_dir/`
7. Also support extracting from a pre-extracted CPK file: `python tools/cpk_extract.py --cpk INGS.CPK --output output_dir/`

## Technical Constraints

- Python 3.8+, dependencies limited to Pillow and NumPy (same as our other tools)
- All binary reads are big-endian: use `struct.unpack('>'...)`
- Follow the project coding standards in `.antigravity/rules.md`
- Include docstrings and comments explaining the format as you parse it
- The tool should print diagnostic info: resolution, frame count, frame rate, audio format

## Disc Image Access

To read files from the disc image, use the ISO9660 sector reader pattern from our project:

```python
SECTOR_SIZE = 2352
HEADER_SIZE = 16
DATA_SIZE = 2048

def read_sector(f, sector_num):
    f.seek(sector_num * SECTOR_SIZE)
    return f.read(SECTOR_SIZE)[HEADER_SIZE:HEADER_SIZE + DATA_SIZE]
```

Parse the ISO9660 filesystem starting from the PVD at sector 16 to locate files. See `docs/QUICK_REFERENCE.md` for the full pattern.

## Validation

After building the tool, test it against the CPK files on Disc 1. Report:
- How many of the 14 CPK files parse successfully
- Resolution and frame count for each
- Whether extracted frames look like valid video (not garbled/corrupted)
- Whether audio extracts correctly

## Deliverables

- `tools/cpk_extract.py` — the complete extraction tool
- A brief update to `docs/PROGRESS.md` marking CPK extraction as complete under Phase 1
- Commit message: `[asset] Add CPK Cinepak video extractor`
