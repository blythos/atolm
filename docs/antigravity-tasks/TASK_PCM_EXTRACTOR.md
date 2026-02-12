# Task: PCM Audio Sample Extractor

## Objective

Create a Python tool (`tools/pcm_extract.py`) that extracts all `.PCM` audio sample files from Panzer Dragoon Saga disc images and converts them to WAV format.

## Context

PDS Disc 1 contains **270 `.PCM` files** — these are audio samples used for sound effects, voice clips, and environmental audio. They are separate from the CPK video audio (which is FMV cutscene audio) and the SEQ sequenced music.

The disc image is at: `ISOs/Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin`

## What We Know

- Saturn audio hardware is the **SCSP** (Saturn Custom Sound Processor), which contains a Yamaha YMF292 DSP and a Motorola 68EC000 CPU
- The SCSP plays PCM samples from its 512KB sound RAM
- Saturn PCM samples are typically: **signed 8-bit or signed 16-bit, big-endian, mono**
- Common sample rates on Saturn: 7680 Hz, 11025 Hz, 15360 Hz, 22050 Hz, 44100 Hz
- The PCM files may or may not have a header — they could be raw sample data or have a Saturn-specific header structure

## Critical Audio Lesson (from CPK extraction)

**Saturn audio is big-endian. WAV is little-endian.** For 16-bit samples, you MUST byte-swap every sample when writing to WAV. This was the primary cause of "static" output in our CPK audio extraction. Do not forget this.

```python
# Correct conversion for 16-bit Saturn PCM → WAV:
import numpy as np
samples = np.frombuffer(raw_data, dtype='>i2')  # big-endian signed 16-bit
samples = samples.astype('<i2')                   # little-endian for WAV
```

For 8-bit signed Saturn audio going to WAV: WAV expects **unsigned** 8-bit. Convert: `wav_byte = saturn_byte + 128`

## Research Needed

The exact format of PDS `.PCM` files is not yet documented in our project. You will need to:

1. **Examine the raw bytes** of several PCM files to determine:
   - Is there a header? (Check for magic bytes, consistent patterns in the first N bytes)
   - Or are they headerless raw sample data?
   - What bit depth? (8-bit or 16-bit)
   - What sample rate? (May need to try several and listen)
   
2. **Cross-reference with yaz0r's Azel project** at https://github.com/yaz0r/Azel — look in `AzelLib/audio/` for any PCM loading code that reveals the format

3. **Check the Saturn SDK documentation patterns** — many Saturn games use a standard audio header format from the Sega sound tools

## Approach

### Step 1: Survey
Extract all 270 PCM files from the disc. Examine the first 64 bytes of each. Look for:
- Common magic bytes or header patterns
- Consistent header size across files
- Whether file sizes suggest 8-bit (size = num_samples) or 16-bit (size = num_samples × 2)

### Step 2: Determine Format
Based on the survey, document the PCM format. If there's a header, parse it for sample rate, bit depth, channels, loop points etc. If headerless, determine reasonable defaults.

### Step 3: Convert to WAV
Write each PCM file as a standard WAV file with correct:
- Sample rate (from header, or best guess with ability to override)
- Bit depth (8 or 16)
- Channel count (likely mono)
- **Correct endianness** (byte-swap 16-bit samples, offset 8-bit samples)

### Step 4: Validate
Play several output WAV files to confirm they sound like game audio (sound effects, voice clips, ambient sounds), not static or garbled data.

## Requirements

1. **Read PCM files from the disc image** using the ISO9660 reader pattern from `docs/QUICK_REFERENCE.md`
2. **Auto-detect format** where possible (header parsing)
3. **Command-line interface**:
   ```
   # Extract all PCM files from disc
   python tools/pcm_extract.py --disc "ISOs/Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin" --output pcm_output/
   
   # Extract a single PCM file
   python tools/pcm_extract.py --disc "ISOs/Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin" --file BATTLE01.PCM --output pcm_output/
   
   # Override sample rate if auto-detection fails
   python tools/pcm_extract.py --pcm raw_file.pcm --rate 22050 --bits 16 --output test.wav
   ```
4. **Print diagnostic info**: file count, detected format, sample rate, duration, bit depth
5. Python 3.8+, only Pillow and NumPy as dependencies (plus `wave` from stdlib)
6. Follow coding standards from `.antigravity/rules.md`

## Deliverables

- `tools/pcm_extract.py` — the extraction tool
- Brief format documentation: add a section to `docs/TECHNICAL_REFERENCE.md` describing the PCM file format as discovered
- Commit message: `[asset] Add PCM audio sample extractor`
