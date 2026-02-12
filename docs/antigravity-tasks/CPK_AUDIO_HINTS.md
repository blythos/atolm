# CPK Audio Extraction — Known Gotchas

The Sega FILM/CPK container has three audio quirks that will produce static or garbled output if not handled. All three are documented at https://multimedia.cx/film-format.txt

## 1. Endian Swap (most likely cause of static)

Saturn CPK audio is **signed 16-bit big-endian PCM**. WAV files expect **signed 16-bit little-endian**. You must byte-swap every 16-bit sample when writing to WAV.

```python
import struct

# For each pair of bytes in the audio data:
# Read as big-endian signed 16-bit, write as little-endian signed 16-bit
for i in range(0, len(audio_data), 2):
    sample = struct.unpack('>h', audio_data[i:i+2])[0]
    wav_data += struct.pack('<h', sample)

# Or more efficiently with numpy:
import numpy as np
samples = np.frombuffer(audio_data, dtype='>i2')  # big-endian int16
samples = samples.astype('<i2')  # convert to little-endian int16
```

## 2. Non-Interleaved Stereo

Standard stereo audio interleaves samples: L R L R L R...

Saturn CPK stereo is **non-interleaved per chunk**. For each audio chunk, the first half is all left channel samples and the second half is all right channel samples:

```
Chunk: [L L L L L L ... R R R R R R ...]
```

To produce standard interleaved WAV stereo, you must split each audio chunk in half and interleave:

```python
half = len(chunk_data) // 2
left_samples = chunk_data[:half]
right_samples = chunk_data[half:]
# Interleave: L R L R L R...
for i in range(0, half, 2):  # 2 bytes per 16-bit sample
    interleaved += left_samples[i:i+2] + right_samples[i:i+2]
```

## 3. Audio Chunks Are Interleaved with Video in the STAB

The STAB (sample table) contains entries for both audio and video chunks interleaved together. You must check each STAB entry to determine whether it's an audio or video chunk:

- Audio chunks have a sample info field that typically has 0xFFFFFFFF in the first 4 bytes of the sample info, or you can identify them by the chunk type flags
- The STAB entry format is 16 bytes: offset(4) + length(4) + sample_info(4) + duration(4)
- For audio: sample_info bytes 0-3 are typically 0xFFFFFFFF
- For video: sample_info bytes 0-3 contain the frame duration in ticks

Collect all audio chunks separately from video chunks, concatenate the audio data, then do the endian swap and stereo deinterleave.

## Quick Test

If your WAV output sounds like static: it's almost certainly the endian swap (issue #1).
If it sounds like audio but distorted/phasing: it's likely the stereo interleaving (issue #2).
If it sounds like audio but with periodic clicks/corruption: you're probably including video chunk data in the audio stream (issue #3).
