# Task: PCM Audio Sample Extractor

## Objective

Create a Python tool (`tools/pcm_extract.py`) that extracts all `.PCM` audio sample files from the Panzer Dragoon Saga disc image and converts them to WAV format.

## Context

PDS Disc 1 contains **270 `.PCM` files** — these are audio samples used for sound effects, voice clips, and environmental audio. They are separate from the CPK video audio (FMV cutscene audio) and the SEQ sequenced music.

The disc image is at: `ISOs/Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin`

## CRITICAL: Do Not Build From Scratch What Already Exists

- Use the Python `wave` module (stdlib) for WAV output. Do not write WAV headers manually.
- Use `numpy` for byte-swapping and sample manipulation.
- Use the ISO9660 disc reader pattern from `docs/QUICK_REFERENCE.md` for reading files from the disc image.
- If you need to play or analyse audio for validation, use `ffprobe` or `ffplay` (from FFmpeg) via subprocess. Ask the user to install FFmpeg if it's not available. Do not write your own audio analysis tools.

## What We Know About Saturn Audio

From our CPK extraction work, we learned:
- Saturn audio is **signed PCM** (both 8-bit and 16-bit are signed)
- 16-bit samples are stored **big-endian**
- WAV format expects **little-endian** 16-bit and **unsigned** 8-bit
- Common Saturn sample rates: 7680, 8000, 11025, 15360, 16000, 22050, 32000, 44100 Hz
- The CPK audio used 32000 Hz — standalone PCM files may use different rates

## Conversion Rules

**16-bit Saturn PCM → WAV:**
```python
import numpy as np
samples = np.frombuffer(raw_data, dtype='>i2')  # big-endian signed 16-bit
samples = samples.astype('<i2')                   # little-endian for WAV
```

**8-bit Saturn PCM → WAV:**
```python
# Saturn 8-bit is signed (-128 to 127). WAV 8-bit is unsigned (0 to 255).
samples = np.frombuffer(raw_data, dtype='int8')
samples = (samples.astype(np.int16) + 128).astype(np.uint8)
```

## Research Needed

The exact format of PDS `.PCM` files is not yet documented. You need to determine:

### Step 1: Survey the files
Extract several PCM files from the disc. Examine the first 64-128 bytes of each in hex. Look for:
- Common magic bytes or header patterns across files
- Consistent header size
- Whether file sizes suggest 8-bit (size ≈ num_samples) or 16-bit (size ≈ num_samples × 2)
- Any embedded sample rate, loop point, or channel count information

### Step 2: Cross-reference with yaz0r's Azel project
Check https://github.com/yaz0r/Azel — look in `AzelLib/audio/` for any PCM loading code. This may reveal whether files have headers or are raw data, and what sample rate/format the game expects.

### Step 3: Determine format by experiment
If the files appear to be headerless raw data:
- Try 16-bit big-endian signed at 22050 Hz first (most common Saturn sound effect rate)
- If that sounds too fast or slow, try 11025, 15360, 16000, 32000
- The sample rate may vary per file — some may be voice (higher rate) vs ambient (lower rate)
- If the files DO have headers, parse them and document the structure

### Step 4: Try FFmpeg/ffprobe first
Before writing any custom detection logic, try:
```python
subprocess.run(['ffprobe', '-i', pcm_file], capture_output=True)
```
FFmpeg may already recognise the format. If it does, you can use `ffmpeg` for conversion and skip writing a custom decoder entirely. Only write custom parsing if FFmpeg can't handle the files.

## CLI Interface

```bash
# Extract all PCM files from disc image
python tools/pcm_extract.py --disc "ISOs/Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin" --output pcm_output/

# Extract a single file
python tools/pcm_extract.py --disc "ISOs/Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin" --file BATTLE01.PCM --output pcm_output/

# Override detection if auto-detect fails
python tools/pcm_extract.py --disc "ISOs/Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin" --rate 22050 --bits 16 --output pcm_output/
```

## Requirements

- Python 3.8+
- Dependencies: `numpy`, `wave` (stdlib)
- Optional: FFmpeg (for validation and fallback conversion) — prompt the user to install it if not found
- Print diagnostic info for each file: detected format, sample rate, bit depth, duration, file size
- Follow coding standards from `.antigravity/rules.md`

## Deliverables

- `tools/pcm_extract.py` — the extraction tool
- Brief format documentation added to `docs/TECHNICAL_REFERENCE.md` describing the PCM format as discovered
- Commit message: `[asset] Add PCM audio sample extractor`
