# Task: CPK Extractor — Revised Approach

## STOP: Do Not Implement a Cinepak Decoder

The previous approach of writing a Cinepak video decoder from scratch has failed. Cinepak is a complex vector quantization codec, and the Saturn "deviant" variant has additional quirks (2 extra header bytes, off-by-8 length fields, modified chunk sizes). FFmpeg's developers spent years getting this right. We should not attempt to reimplement it.

## Correct Approach: Two-Track

### Track 1: Use FFmpeg for video conversion (practical output)

FFmpeg already has a working Sega FILM demuxer and Saturn-variant Cinepak decoder. Use it:

```python
import subprocess

def convert_cpk_to_mp4(cpk_path, output_path):
    """Convert a Saturn CPK file to MP4 using FFmpeg."""
    subprocess.run([
        'ffmpeg', '-i', cpk_path,
        '-c:v', 'libx264', '-crf', '18',
        '-c:a', 'aac', '-b:a', '192k',
        '-y', output_path
    ], check=True)
```

The tool should:
1. Extract CPK files from the disc image (using our ISO9660 reader)
2. Save them as standalone .cpk files
3. Call FFmpeg to convert to MP4 (or PNG frames + WAV)
4. If FFmpeg is not installed, output the raw .cpk files with instructions

### Track 2: Parse the Sega FILM container ourselves (for decompilation knowledge)

We DO want to understand and parse the container format, because our decompilation needs to know how the game loads and plays these files. But we don't need to decode the Cinepak bitstream — that's the Saturn hardware's job, not the game code's.

Parse and document:
- FILM header (magic, version, size)
- FDSC chunk (video codec, dimensions, audio format)
- STAB chunk (sample table — frame offsets, sizes, timestamps, audio/video flags)
- Report: resolution, frame count, frame rate, audio format, duration

## Audio: It's Almost Certainly PCM, Not ADPCM

The previous attempt identified compression type `0x18` (24 decimal). This is very likely a **misread of the FDSC chunk**. Here is the correct FDSC layout:

```
bytes 0-3:   'FDSC' signature
bytes 4-7:   chunk length (32 = 0x20)
bytes 8-11:  video FOURCC ('cvid' or null)
bytes 12-15: video height
bytes 16-19: video width
byte 20:     bits per pixel (always 24 for video)
byte 21:     audio channels (1=mono, 2=stereo)
byte 22:     audio bit depth (8 or 16)
byte 23:     audio compression (0=PCM, 2=ADX ADPCM)
bytes 24-27: audio sample rate
```

**Note**: byte 20 is VIDEO bits per pixel (24 = standard). The audio compression is at byte 23. PDS almost certainly uses compression=0 (plain PCM). The only known Saturn games with ADPCM in CPK files are Burning Rangers, Lunar 2, and Utena.

If audio compression is 0 (PCM), the audio data in each audio chunk is raw PCM with these properties:
- **Signed** (both 8-bit and 16-bit are signed on Saturn)
- **Big-endian** if 16-bit
- **Non-interleaved stereo** if stereo (first half = left channel, second half = right channel)

To write WAV:
- 16-bit: byte-swap every sample from big-endian to little-endian
- 8-bit: convert from signed to unsigned (add 128 to each byte)
- Stereo: interleave left and right channels

```python
import numpy as np

# For 16-bit PCM audio chunks:
samples = np.frombuffer(audio_chunk_data, dtype='>i2')  # big-endian signed 16
samples = samples.astype('<i2')  # little-endian for WAV

# For stereo, deinterleave per chunk:
half = len(samples) // 2
left = samples[:half]
right = samples[half:]
interleaved = np.empty(len(samples), dtype='<i2')
interleaved[0::2] = left
interleaved[1::2] = right
```

## Identifying Audio vs Video Chunks in STAB

Each STAB entry is 16 bytes:
```
bytes 0-3:   sample offset (from start of data section)
bytes 4-7:   sample length
bytes 8-11:  sample info 1 (0xFFFFFFFF for audio, timestamp for video)
bytes 12-15: sample info 2 (1 for audio, frame duration for video)
```

Audio chunks: sample_info_1 == 0xFFFFFFFF
Video chunks: sample_info_1 != 0xFFFFFFFF

## Deliverables

- `tools/cpk_extract.py` with:
  - ISO9660 disc reader to extract CPK files
  - Sega FILM container parser (FILM + FDSC + STAB)
  - Audio extractor (PCM → WAV with correct endianness)
  - FFmpeg wrapper for video conversion
  - Diagnostic output (resolution, frame count, fps, audio format, duration)
- CLI: `python tools/cpk_extract.py --disc disc1.bin --output cpk_output/`
- Commit message: `[asset] Add CPK Cinepak video extractor`

## Validation

- All 14 CPK files on Disc 1 should extract without errors
- FFmpeg conversion should produce watchable MP4 files showing PDS cutscenes
- Audio WAV files should sound like speech/music, not static
- Container parser should correctly report resolution, frame rate, and audio format for each file
