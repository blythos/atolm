# Task: SEQ/TON Sequenced Music Extractor

## Objective

Create a Python tool (`tools/seq_extract.py`) that extracts all sequenced music data from Panzer Dragoon Saga disc images and converts it to playable formats:
- SEQ → Standard MIDI (.mid)
- TON/BIN → WAV samples (.wav) + DLS or SF2 soundfont
- Optionally render complete tracks to WAV using the extracted MIDI + samples

## Context

Panzer Dragoon Saga uses Sega's **CyberSound** sound system for its in-game music. CyberSound is the standard Saturn sequenced audio framework, running on the **SCSP** (Saturn Custom Sound Processor) chip's embedded **Motorola 68EC000** CPU. It works like MIDI: small sequence files contain note events and control changes, while separate tone/sample bank files contain the actual PCM instrument waveforms that the SCSP plays back through its 32 channels.

The disc image is at: `ISOs/Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin`

This is the same raw Mode 2 CD-ROM format used by all our other extraction tools (2352 bytes/sector: 16 header + 2048 data + 288 ECC). Use the project's existing ISO9660 reader if available, or implement basic sector reading.

## What's On Disc

Disc 1 contains:
- **Standalone `.SEQ` files** — individual sequence files in the filesystem
- **`.BIN` files paired with `.SEQ` files** — tone/sample banks (NOT the same as other .BIN files on disc; these are specifically the ones that correspond to SEQ files by name or directory grouping)
- **`.SND` bundle files** — concatenated archives containing multiple SEQ banks, TON banks, and DSP program banks packed together. Known SND files on Disc 1 include:
  - `EPISODE1.SND`, `EPISODE2.SND`, `EPISODE3.SND`, `EPISODE4.SND`
  - `INTER12.SND`, `INTER23.SND`, `INTER35.SND` (inter-episode transitions)
  - Possibly others

**Important:** Not all `.BIN` files on disc are tone banks. Many are generic binary data. The tone banks are specifically the ones associated with SEQ files (co-located in the same directory, similar naming, or referenced by SND bundles).

## File Formats

### SEQ (Sequence) Format — "Saturn Sequence 2.00"

The SEQ format is very close to Standard MIDI File (SMF) Format 0, with some Saturn-specific modifications. Key facts:

- **Magic/identification**: SEQ files can be identified by scanning for the sequence header. The tool `seqext` (by kingshriek) identifies them by signature patterns. CyberWarriorX's `seq2mid` documentation describes the format in detail.
- **Structure**: MIDI-like event stream with note-on/off, control changes, program changes, pitch bend, etc.
- **Timing**: Uses MIDI-style delta-time encoding
- **Saturn-specific events**: Some control events are CyberSound extensions (DSP effect sends, SCSP-specific parameters). These should be preserved as MIDI SysEx or meta events where possible, or logged and skipped.
- **Banks**: A single SEQ file or SND bundle can contain multiple sequence banks (multiple songs/sound effect sets)

**Reference implementation**: `seq2mid` by CyberWarriorX (maintained fork at github.com/mistydemeo/seq2mid). This is a C program that converts SEQ → MIDI. Study its source code for format details, particularly:
- How it identifies SEQ data boundaries
- How it maps CyberSound events to MIDI events
- How it handles multi-bank SEQ files
- Known quirks and edge cases (the readme mentions Langrisser DE requiring special handling)

### TON (Tone) Format — Instrument Sample Banks

TON files contain PCM sample data plus instrument definitions that tell the SCSP how to play each sample (pitch, loop points, volume envelopes, etc.).

- **In PDS**: Tone banks are stored as `.BIN` files, NOT `.TON` — this is a PDS-specific naming choice. The format is the same as standard CyberSound TON.
- **Contents**: Raw PCM sample waveforms (typically 8-bit or 16-bit, various sample rates) plus metadata (root key, loop start/end, ADSR envelope, etc.)
- **Saturn audio is big-endian**: 16-bit PCM samples are stored big-endian. When exporting to WAV, you MUST byte-swap every 16-bit sample to little-endian. For 8-bit signed Saturn audio going to WAV: WAV expects unsigned 8-bit (add 128 to each sample).
- **Reference implementation**: `TONCNV` by CyberWarriorX converts TON → DLS (DownLoadable Sound) or individual WAV files. His readme notes: "Keep in mind that not all ton files are properly converted. Stuff like Frequency Modulation, ADSR, etc. aren't really even tackled."

### SND (Sound Bundle) Format

SND files are concatenated archives containing multiple banks:
- **TON banks** (instrument samples)
- **SEQ banks** (sequence data)  
- **DSP banks** (SCSP DSP effect programs, typically 0x540 bytes each)

There is **no header** describing the bundle layout. The game's sound driver code knows the offsets. However, the community has reverse-engineered the layouts for PDS USA disc:

**Known SND layout — EPISODE2.SND (USA disc):**
```
TON bank 0 at 0x00000, length 0x2F026
TON bank 1 at 0x2F026, length 0x0DE60
SEQ bank 0 at 0x4D100, length 0x0129A
TON bank 2 at 0x5FAAA, length 0x13D10
SEQ bank 1 at 0x737BA, length 0x004F0
SEQ bank 2 at 0x73CAA, length 0x006E2
DSP bank 0 at 0x7438C, length 0x00540
DSP bank 1 at 0x748CC, length 0x00540
```

**Known SND layout — EPISODE4.SND (USA disc):**
```
SEQ bank 0 at 0x00000, length 0x10000
DSP bank 0 at 0x10000, length 0x00540
SEQ bank 1 at 0x10540, length 0x004F0
TON bank 0 at 0x21100, length 0x2F676
SEQ bank 2 at 0x50776, length 0x00500
TON bank 1 at 0x50C76, length 0x0E000
TON bank 2 at 0x5EC76, length 0x16350
```

**Known SND layout — INTER23.SND (USA disc):**
```
SEQ bank 0 at 0x00000, length 0x00060
TON bank 0 at 0x00060, length 0x46500
SEQ bank 1 at 0x46560, length 0x004EC
TON bank 1 at 0x57100, length 0x0DE60
SEQ bank 2 at 0x64F60, length 0x00200
TON bank 2 at 0x65160, length 0x0A000
DSP bank 0 at 0x6F160, length 0x00540
```

Note: The banks are NOT in a consistent order across different SND files (some start with TON, others with SEQ). You cannot assume a fixed layout.

**Strategy for unknown SND files**: 
1. Use the known layouts above as ground truth for validation
2. For unknown SND files, try heuristic detection:
   - SEQ banks can be identified by their header signatures (study seq2mid source)
   - DSP banks are consistently 0x540 bytes and have recognizable structure
   - TON banks contain PCM sample data — look for the tone bank header structure (study TONCNV source)
   - Gaps/padding between banks are common (often aligned to sector boundaries or round addresses)
3. As a fallback, extract the raw SND file and let the user specify offsets manually

## SCSP Sound RAM Context

The SCSP has 512KB of sound RAM. The 68000 CPU manages loading TON banks into this RAM and playing SEQ events. The game's sound driver (running on the 68000) handles:
- Loading the appropriate TON bank into SCSP RAM
- Parsing SEQ events and triggering SCSP channels
- Managing DSP effects
- Mixing and output

For our purposes, we don't need to emulate the SCSP or 68000. We just need to:
1. Extract the raw SEQ and TON data
2. Convert SEQ → MIDI
3. Convert TON → WAV samples + DLS/SF2 soundfont
4. Optionally render the complete track using a software MIDI synthesizer with the extracted soundfont

## Implementation Plan

### Phase 1: Disc Scanning and File Cataloguing

1. Read the ISO9660 filesystem and list all `.SEQ`, `.SND`, and candidate `.BIN` files
2. Identify which `.BIN` files are likely tone banks:
   - Co-located with `.SEQ` files
   - Reasonable size for sample data (typically 10KB–500KB)
   - NOT files that are known to be other formats (MCB, CGB, SCB, PNB, PRG)
3. Output a catalogue: `{seq_file: corresponding_ton_file}` pairs plus standalone SND bundles

### Phase 2: Standalone SEQ/BIN Extraction

1. For each standalone SEQ file, convert to MIDI
2. For each corresponding BIN (tone) file, extract to individual WAV samples + DLS
3. Output directory structure:
```
output/seq/
  TRACKNAME/
    TRACKNAME.mid          # MIDI conversion
    TRACKNAME.dls          # DLS soundfont (if feasible)
    samples/
      000_instrument.wav   # Individual sample WAVs
      001_instrument.wav
      ...
    info.json              # Metadata: sample rates, loop points, channel assignments
```

### Phase 3: SND Bundle Unpacking

1. For SND files with known layouts (EPISODE2, EPISODE4, INTER23), use the hardcoded offsets above
2. For SND files with unknown layouts, attempt heuristic bank detection
3. Extract each bank to its own file, then process SEQ and TON banks as in Phase 2
4. Log DSP bank data for future use (we'll need these when reimplementing the audio engine)

### Phase 4: Optional Audio Rendering

If time permits, render complete tracks:
1. Load MIDI + DLS/SF2 into a Python MIDI synthesizer (e.g., `fluidsynth` via `pyfluidsynth`, or `midi2audio`)
2. Render to WAV at 44100Hz stereo
3. This gives us listenable tracks without needing a DAW

## Critical Technical Reminders

1. **Saturn audio is big-endian.** All 16-bit PCM samples in TON banks are big-endian. WAV is little-endian. SWAP EVERY SAMPLE. This was the #1 cause of broken audio in our CPK extraction work.

```python
import numpy as np
samples = np.frombuffer(raw_data, dtype='>i2')  # big-endian signed 16-bit
samples = samples.astype('<i2')                   # little-endian for WAV
```

2. **8-bit signed → unsigned**: Saturn uses signed 8-bit PCM. WAV 8-bit format expects unsigned. Add 128 to each byte.

3. **Sample rates vary**: Saturn SCSP supports arbitrary sample rates. Common values: 7680, 11025, 15360, 22050, 44100 Hz. The sample rate is stored in the tone bank instrument definition, not the raw sample data. If you can't determine the rate, default to 22050 Hz and note it in the output metadata.

4. **Loop points matter**: Many instrument samples are looped (sustained notes). The loop start/end points are in the tone bank metadata. Export these in the info.json and in the DLS/SF2 file. WAV files should be exported as the full sample (not looped).

## Reference Tools and Code

Study these existing implementations before writing code:

1. **seq2mid** (github.com/mistydemeo/seq2mid) — C source for SEQ → MIDI conversion. The most important reference for understanding the SEQ binary format. Read `decode.c` carefully.

2. **TONCNV** (CyberWarriorX, cyberwarriorx.com) — Converts TON → DLS + WAV. Study for the TON bank header structure and sample extraction logic.

3. **seqext.py / tonext.py** (kingshriek, part of the SSF toolchain) — Python scripts for extracting SEQ/TON data from disc images. These scan binary files for SEQ/TON signatures. Available via VGMToolbox or the SSF tools archive.

4. **ssfmake.py** (kingshriek) — Creates SSF files from extracted SEQ/TON data. Contains sound map definitions that document the SCSP RAM layout expectations for different games.

5. **VGMToolbox** — Has a frontend for seqext/tonext that can scan entire disc contents.

## Constraints

1. Python 3.8+, minimal dependencies. NumPy for sample manipulation, `wave` from stdlib for WAV output. `mido` library is acceptable for MIDI file writing (it's well-maintained and pure Python).
2. No dependency on the C tools above — they are **reference only**. We write our own Python implementation, but we use their source code to understand the binary formats.
3. All file I/O must handle the raw disc image format (2352 bytes/sector) OR pre-extracted files. Support both modes:
   - `--iso PATH` reads directly from the disc image
   - `--input PATH` reads a pre-extracted file or directory
4. Print diagnostic info for every file processed: type, bank count, sample count, sample rates, durations
5. Follow coding standards from `.antigravity/rules.md`
6. Graceful degradation: if a particular SEQ has unknown events, log them and continue (don't crash). If a TON bank can't be fully parsed, extract what you can and note the failures.

## Validation

### Must pass:
- [ ] Correctly identifies and catalogues all SEQ/BIN/SND files on Disc 1
- [ ] Extracts standalone SEQ files to playable MIDI files (open in any MIDI player/DAW)
- [ ] Extracts tone bank samples to WAV files that sound like instruments (not static/noise)
- [ ] Correctly unpacks EPISODE2.SND using the known offsets and extracts valid SEQ/TON banks
- [ ] Correctly unpacks EPISODE4.SND and INTER23.SND using known offsets
- [ ] Heuristic SND unpacking produces reasonable results for EPISODE1.SND and EPISODE3.SND
- [ ] All 16-bit WAV output is correctly byte-swapped (no static)
- [ ] All 8-bit WAV output is correctly unsigned (no crackling/clipping)

### Stretch goals:
- [ ] DLS or SF2 soundfont generation from tone banks
- [ ] Rendered WAV tracks using fluidsynth or equivalent
- [ ] SNDTEST.PRG cross-reference: there's a hidden sound test overlay on Disc 1 (SNDTEST.PRG) that contains the names of music files — extract the track name table and use it to label output files
- [ ] DSP bank extraction and documentation (even if we can't use them yet, cataloguing them is useful)

## Deliverables

- `tools/seq_extract.py` — the main extraction tool
- Format documentation: add a section to `docs/TECHNICAL_REFERENCE.md` describing the SEQ, TON, and SND formats as understood
- Example output: at least 3 tracks fully extracted with MIDI + WAV samples
- Commit message: `[asset] Add SEQ/TON sequenced music extractor`

## Known Community Resources

- SSF rips of PDS exist on Zophar's Domain — these are savestate-based captures of the SCSP state, not raw file extractions, but they prove the music IS sequenced (not streamed)
- Someone on Panzer Dragoon Legacy forums successfully extracted MIDI + DLS from PDS using seq2mid + TONCNV circa 2011 and confirmed the results sound very close to the original, minus reverb/delay effects and with minor volume/panning differences
- Someone on SegaXtreme successfully extracted MIDI from PDS Zwei and Saga as recently as 2025, with updated seq2mid versions
- The PDS CDs contain SNDTEST.PRG which is a hidden/unused sound test program containing track name references
