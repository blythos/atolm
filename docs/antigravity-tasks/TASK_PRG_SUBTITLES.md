# Task: Extract FMV Subtitle Text and Timing from PRG Overlay Files

## Project Context

This is part of the Panzer Dragoon Saga (Sega Saturn, 1998) decompilation project. Repository: https://github.com/blythos/atolm

Read these files from the repo before starting:
- `docs/PROJECT_INSTRUCTIONS.md` — full format specs, architecture, established knowledge
- `docs/TECHNICAL_REFERENCE.md` — binary format details, fixed-point math, Saturn conventions
- `docs/QUICK_REFERENCE.md` — code snippets for disc reading and common operations
- `.antigravity/rules.md` — critical technical facts (endianness, formats, etc.)

## The Problem

PDS has 14 Cinepak FMV cutscenes (.CPK files) on Disc 1. The dialogue is spoken in Japanese/Panzerese and the English subtitles are displayed by the game engine as VDP2 text overlays during video playback. The subtitle text and display timing are NOT in the CPK files — they're in the PRG overlay files (SH-2 executable code that controls each scene).

We've already extracted the CPK videos to MP4 with working audio/video. Now we need to extract the subtitle text and frame-accurate timing so we can generate SRT files and mux them into the MP4s.

## What We Know (Research Complete)

### PDS Script System — Fully Documented from yaz0r's Azel

The game uses a **bytecode script interpreter** embedded within each PRG overlay. This has been fully reverse-engineered from `AzelLib/town/townScript.cpp` in yaz0r's Azel project (https://github.com/yaz0r/Azel). The script system controls all scene flow: NPC dialogue, cutscene timing, FMV playback, and subtitle display.

**Key source files in yaz0r's Azel (already analysed):**
- `AzelLib/town/townScript.cpp` — Complete script bytecode interpreter (`runScript()` function, lines 1661–2043). This is the single most important reference file.
- `AzelLib/town/e006/twn_e006.cpp` — FMV/cutscene playback system. Contains `createEPKPlayer()` which starts FMV playback, and `getCutsceneFrameIndex()` which returns the current video frame.
- `AzelLib/town/e006/twn_e006.h` — `sStreamingFile` struct definition. Field `m28.m84_frameIndex` is the current frame counter.
- `AzelLib/kernel/textDisplay.cpp` — VDP2 text rendering functions (`VDP2DrawString`, `clearVdp2TextArea`).
- `AzelLib/common.cpp` line 353 — `readSaturnString()`: reads null-terminated byte strings from Saturn memory. Text is plain null-terminated ASCII in the USA version.

### Script Bytecode Format

The script is a stream of opcodes with inline data. Opcodes are 1 byte. Data arguments follow with alignment padding. Here are the opcodes relevant to FMV subtitles:

| Opcode | Name | Format | Description |
|--------|------|--------|-------------|
| 1 | end | (none) | End script / return from subroutine |
| 2 | wait | `02` + align16 + `u16 delay` | Pause execution for N frames |
| 3 | jump | align32 + `u32 target_ptr` | Unconditional jump |
| 5 | if | align32 + `u32 target_ptr` | Jump to target if `currentResult == 0` |
| 6 | callScript | align32 + `u32 target_ptr` | Push return addr, jump to target |
| 7 | callNative | `u8 numArgs` + align32 + `u32 funcAddr` + `u32[numArgs] args` | Call native C function |
| 8 | equal | align16 + `s16 value` | Set `currentResult = (value == currentResult)` |
| 25 | addCinematicBars | (none) | Start cinematic letterbox bars |
| 26 | removeCinematicBars | (none) | Remove cinematic letterbox bars |
| **27** | **drawString** | align32 + `u32 string_ptr` | **Display subtitle text at bottom of screen** |
| **29** | **clearString** | (none) | **Clear the current subtitle text** |
| 32 | waitFade | (none) | Wait for screen fade to complete |
| 33 | playSFX | `s8 sfx_id` | Play system sound effect |
| 34 | playPCM | `s8 pcm_id` | Play PCM audio sample |
| **36** | **displayTimedString** | align16 + `s16 duration` + align32 + `u32 string_ptr` | Display text for N frames then auto-clear |
| **46** | **cutsceneFrameSync** | align16 + `s16 frame_number` | **Wait until FMV reaches frame N** (the key timing opcode) |

**Alignment rules:**
- `align16`: advance to next 2-byte boundary (offset = (offset + 1) & ~1)
- `align32`: advance to next 4-byte boundary (offset = (offset + 3) & ~3)

### How FMV Subtitles Work — The Full Pipeline

A typical FMV subtitle sequence in the script bytecode looks like:

```
07 01 <align32> <funcAddr=createEPKPlayer> <arg=cpk_filename_ptr>   ; Start FMV playback
2E <align16> 0030                                                    ; opcode 46: wait until frame 48
1B <align32> <string_ptr>                                            ; opcode 27: draw "First subtitle line"
2E <align16> 0090                                                    ; opcode 46: wait until frame 144
1D                                                                   ; opcode 29: clear subtitle
2E <align16> 0096                                                    ; opcode 46: wait until frame 150
1B <align32> <string_ptr>                                            ; opcode 27: draw "Second subtitle line"
...
```

**Note on opcode hex values:** Opcodes are stored as raw bytes. Opcode 27 = 0x1B, opcode 29 = 0x1D, opcode 46 = 0x2E, opcode 36 = 0x24, opcode 7 = 0x07. Use hex values when scanning binary data!

So the pattern is:
1. **opcode 7** calls `createEPKPlayer(filename_ptr)` — starts FMV playback
2. **opcode 46** waits until the video reaches a specific frame number
3. **opcode 27** displays a subtitle string (pointed to by a 32-bit address within the PRG)
4. **opcode 46** waits until the next cue point
5. **opcode 29** clears the subtitle, OR **opcode 27** replaces it with the next line
6. Repeat until the FMV ends

### String Encoding

In the USA version, text strings are **plain null-terminated ASCII** stored within the PRG file's data section. The `readSaturnString()` function (common.cpp:353) simply reads bytes until it hits a null terminator. **No custom font encoding is needed for extraction** — the strings are directly human-readable.

The string pointers in the script bytecode are 32-bit Saturn memory addresses (typically 0x0605XXXX or 0x0606XXXX range for PRG overlays loaded at those base addresses). To find the actual offset within the PRG file, subtract the overlay's load address.

### PRG Load Addresses

PRG overlays are loaded to specific addresses in Saturn Work RAM. The common load addresses are:
- `0x06010000` — some overlays
- `0x06050000` — many field/town overlays
- Other addresses depending on the overlay

The load address can usually be determined by examining the pointer values within the PRG: the first few u32 values in the pointer table will be absolute addresses, and the base address is the lowest aligned address that makes all pointers fall within the file.

### CPK Filenames — Disc 1

From the Panzer Dragoon Legacy FMV script, the CPK files follow the naming pattern `movie1.cpk`, `evt000_1.cpk` through `evt000_5.cpk`, `evt002.cpk`, `evt004_1.cpk`, `evt004_2.cpk`, etc. Disc 1 has 14 CPK files. List them from the disc image to get exact names.

The CPK filename is stored as a null-terminated string within the PRG and passed as an argument to `createEPKPlayer` via script opcode 7.

## Implementation Strategy

### Step 1: Extract and scan PRG files

Extract all 59 PRG files from the disc image. For each PRG:
1. Scan for ASCII strings (sequences of 4+ printable bytes followed by null)
2. Look for known subtitle text fragments: "Thousands of years", "The age started anew", "What's up, Edge", "the Empire", "excavation", etc.
3. Look for CPK filenames: scan for `.CPK` or `.cpk` byte sequences

### Step 2: Identify FMV-controlling PRGs

For each PRG that contains a CPK filename string:
1. Record which CPK file(s) it references
2. Determine the PRG's load base address by examining its internal pointer values
3. Map: PRG filename → CPK filename(s) → scene description

### Step 3: Parse script bytecode to extract subtitles

For each FMV-controlling PRG:
1. Locate the script data section (look for concentrations of known opcodes: 0x2E frame syncs, 0x1B draw strings, 0x1D clear strings)
2. Parse the bytecode linearly, tracking:
   - Frame sync points (opcode 0x2E → frame number)
   - String display points (opcode 0x1B → string pointer → resolve to text)
   - String clear points (opcode 0x1D)
   - Timed string display (opcode 0x24 → duration + string pointer)
3. Build a timeline: `[(start_frame, end_frame, "subtitle text"), ...]`

The end_frame for each subtitle is either:
- The frame of the next clear (opcode 0x1D)
- The frame of the next string draw (opcode 0x1B replaces the current text)
- The start_frame + duration (for timed strings, opcode 0x24)

### Step 4: Convert frame numbers to timestamps

The CPK files use Cinepak FILM container format with variable frame timing. Each frame has a tick count in the STAB (Sample Table) chunk. To convert frame numbers to timestamps:
1. Parse the STAB from the CPK file to get per-frame timing
2. Cumulative sum of tick durations gives the timestamp for each frame
3. Convert to SRT format: `HH:MM:SS,mmm`

If the STAB parsing is too complex, assume a nominal frame rate. The FMV likely runs at approximately 15 fps (common for Saturn Cinepak). Verify by checking STAB data from the existing CPK extractor.

### Step 5: Generate SRT files

Standard SRT format:
```
1
00:00:05,000 --> 00:00:08,500
The age started anew.

2
00:00:09,000 --> 00:00:13,000
The people rejoiced, believing
that humans could live without fear.
```

### Step 6: Mux into MP4s

Use ffmpeg:
```bash
ffmpeg -i video.mp4 -i subtitles.srt -c copy -c:s mov_text output.mp4
```

## Reference: Known FMV Dialogue Text

The complete dialogue text (without timing) is published at:
https://www.panzerdragoonlegacy.com/literature/727-panzer-dragoon-saga-fmv-script

Use this to verify extracted text is correct and complete. The relevant Disc 1 FMVs and their content:

- **movie1.cpk** — Intro movie before title screen (no dialogue, just narration text)
- **evt000_1.cpk** — Edge and Rhua at Excavation Site #4 (extensive dialogue)
- **evt000_2.cpk** — Craymen's fleet, narrator exposition (heavy narration + dialogue)
- **evt000_3.cpk** — Monster fight in the excavation (some dialogue)
- **evt000_4.cpk** — Craymen takes over the site (dialogue)
- **evt000_5.cpk** — Imperial Capital destruction (dialogue)
- **evt002.cpk** — Edge wakes up in ruins (brief dialogue)
- **evt004_1.cpk** — Canyon ambush (no dialogue?)
- **evt004_2.cpk** — Dragon vision (brief dialogue)
- Other CPKs depend on which 14 are on Disc 1.

## Important Notes on Bytecode Scanning

**The PRG files contain SH-2 machine code AND embedded data.** The script bytecode is in a DATA section, not interleaved with SH-2 instructions. You cannot just scan the entire file for opcode patterns — you'd get false positives from SH-2 code that happens to contain the same byte values.

**Strategy for finding the script data:**
1. First, locate string data (ASCII text). The strings are typically in the latter portion of the PRG.
2. The script bytecodes that reference those strings will have pointers pointing INTO the string area.
3. Look for sequences of opcode 0x2E (frame sync) followed by opcode 0x1B (draw string) — this pattern is distinctive and unlikely to appear randomly in SH-2 code.
4. The script section is typically a contiguous block. Once you find the start, you can parse it linearly.

**Pointer resolution:** String pointers in the bytecode are absolute Saturn addresses (e.g., `0x0605A3C0`). To get the file offset: `file_offset = saturn_address - load_base_address`. The load base can be inferred from examining the pointer values — they should all fall within a consistent `base..base+filesize` range.

## Disc Image Location

The disc image is at: `ISOs/Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin`

## Tools Available

- Python 3.8+ with numpy, Pillow, struct
- FFmpeg (installed) for video/subtitle muxing
- The working CPK extractor at `tools/cpk_extract.py`
- The disc image with all PRG, CPK, FNT files accessible
- yaz0r's Azel repo cloned locally (reference only, do not depend on it)

## Expected Deliverables

1. **Documentation** of the PDS script bytecode format and FMV subtitle system (added to `docs/TECHNICAL_REFERENCE.md`)
2. **A Python tool** (`tools/prg_subtitle_extract.py`) that:
   - Reads a PRG file from disc
   - Auto-detects the load base address
   - Locates and parses the script bytecode
   - Extracts all subtitle text with frame-accurate timing
   - Outputs SRT files
3. **Generated SRT files** for all Disc 1 FMVs that contain dialogue
4. **A companion script or update to cpk_extract.py** that muxes the SRTs into the MP4s

## Validation

Cross-reference all extracted subtitle text against the Panzer Dragoon Legacy FMV script. Every line of dialogue listed there for Disc 1 FMVs should appear in the extracted SRTs. Missing or garbled text indicates a parsing error.

## What NOT to Do

- Don't try to fully disassemble the SH-2 code in the PRGs. The subtitle data is in the SCRIPT bytecode sections, not in the machine code.
- Don't assume a fixed frame rate without checking. Saturn Cinepak FMVs commonly use variable frame timing.
- Don't write a general-purpose SH-2 disassembler. That's a separate task.
- Don't modify the core model/texture extraction pipeline. This task is purely about PRG text and timing extraction.
