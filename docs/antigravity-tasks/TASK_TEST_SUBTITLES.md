# Task: Test and Fix the FMV Subtitle Extractor

## Project Context

This is part of the Panzer Dragoon Saga decompilation project. Repository: https://github.com/blythos/atolm

Read these files from the repo before starting:
- `.antigravity/rules.md` — critical technical facts
- `docs/PROJECT_INSTRUCTIONS.md` — full format specs

## Background

The subtitle extractor (`tools/extract_subtitles.py`) has been rewritten to use a dual-strategy approach:

1. **PRG bytecode parsing** (primary): Parses the game's script bytecode from PRG overlay files to extract frame-accurate subtitle timing and text. This is based on the fully-documented script interpreter from yaz0r's Azel project (`AzelLib/town/townScript.cpp`).

2. **MOVIE.DAT table** (fallback): Reads a flat subtitle table from MOVIE.DAT, with CPK ordering from MOVIE.PRG. Groups map 1:1 to CPK files.

The tool replaces the previous broken version that was incorrectly trying to split subtitle groups across CPKs based on STAB frame counts.

## What You Need to Do

### Step 1: Run the extractor and capture all output

Run ALL THREE modes and save the full output of each:

```bash
cd /path/to/atolm

# Mode 1: Both (PRG primary, DAT fallback)
python tools/extract_subtitles.py --iso "ISOs/Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin" --output output/subtitles --verbose --method both 2>&1 | tee test_both.log

# Mode 2: PRG only
python tools/extract_subtitles.py --iso "ISOs/Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin" --output output/subtitles_prg --verbose --method prg 2>&1 | tee test_prg.log

# Mode 3: DAT only
python tools/extract_subtitles.py --iso "ISOs/Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin" --output output/subtitles_dat --verbose --method dat 2>&1 | tee test_dat.log
```

### Step 2: Validate SRT file content

For each SRT file generated, check:

1. **File naming**: SRT files must be named to match CPK files exactly (e.g., `EVT000_1.srt` for `EVT000_1.CPK`). The `cpk_extract.py` tool looks for SRTs in `output/subtitles/` with matching names.

2. **Text content**: Open each SRT and verify the subtitle text is readable English, not garbage. Compare against the known FMV script at: https://www.panzerdragoonlegacy.com/literature/727-panzer-dragoon-saga-fmv-script

3. **Timing sanity**: Frame numbers should be monotonically increasing within each SRT. Start times should be before end times. No subtitle should start at frame 0 unless it's genuinely the first line of dialogue in the video.

4. **Coverage**: Disc 1 has 14 CPK files. The following are known to have subtitles:
   - `MOVIE1.CPK` — Intro narration (may or may not have subs in this format)
   - `EVT000_1.CPK` through `EVT000_5.CPK` — Opening sequence (extensive dialogue)
   - `EVT002.CPK` — Edge wakes up
   - Other EVT files on Disc 1

   Not all CPKs have subtitles (some are pure action sequences with no dialogue). An SRT file with 0 subtitles should not be generated.

### Step 3: Test the full pipeline (subtitles muxed into video)

Run the CPK extractor with the subtitle output in place:

```bash
# First generate subtitles
python tools/extract_subtitles.py --iso "ISOs/Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin" --output output/subtitles --method both

# Then extract videos (which will auto-detect SRTs in output/subtitles/)
python tools/cpk_extract.py --disc "ISOs/Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin" --output output/videos
```

Check the FFmpeg output for each video — it should show `Found Subtitles: output/subtitles/XXXXX.srt` for files that have subtitle tracks. Verify by playing one of the resulting MP4s in a video player and enabling subtitles.

### Step 4: Report results

Create a file `docs/SUBTITLE_TEST_RESULTS.md` with:

1. **Summary table**: For each CPK on disc, list:
   - CPK filename
   - Method that found subtitles (PRG / DAT / none)
   - Number of subtitle entries
   - First subtitle text (first 50 chars)
   - Whether the text looks correct (yes/no/partial)

2. **PRG parsing log**: Which PRGs were scanned, which had CPK references, which had valid script regions, how many events were parsed

3. **Issues found**: Any problems with timing, text content, missing subtitles, or crashes. Include the exact error messages.

4. **Comparison**: If both PRG and DAT methods produced results for the same CPK, do they agree on the subtitle text and approximate timing?

## Important Notes

### Do NOT modify the core extraction logic

If the PRG bytecode parser fails to find subtitles, **do not rewrite the parser**. Instead:
- Document exactly what happened (which PRG, what output, what error)
- Check if the DAT fallback covered it
- Report the gap so it can be fixed by Claude in the next session

### The cpk_extract.py SRT lookup paths

The CPK extractor looks for SRT files in these locations (in order):
```python
srt_search_paths = [
    os.path.join("output/subtitles", srt_name),
    os.path.join("subtitles", srt_name)
]
```

The `srt_name` is derived from the CPK filename: `EVT000_1.CPK` → `EVT000_1.srt`. Make sure the subtitle extractor outputs to `output/subtitles/` (the default).

### Known technical details

- FMV frame rate is approximately 15 fps (the `--fps 15` default is correct)
- All data is big-endian (SH-2 native byte order)
- String encoding in the USA version is plain null-terminated ASCII
- PRG files are loaded to Saturn Work RAM addresses (typically 0x0605XXXX or 0x0604XXXX range)
- The MOVIE.DAT base address is typically 0x00250000

### If the tool crashes

If the tool crashes with a Python exception:
1. Save the full traceback
2. Note which PRG file or stage caused the crash
3. Try running with `--method dat` to see if the DAT fallback works independently
4. Include all of this in the test results

## Validation Checklist

- [ ] All three modes run without crashing
- [ ] SRT files are generated in `output/subtitles/`
- [ ] SRT filenames match CPK filenames exactly (case-insensitive, but uppercase preferred)
- [ ] Subtitle text is readable English (not binary garbage)
- [ ] Timing increases monotonically within each file
- [ ] `cpk_extract.py` finds and muxes the SRTs into MP4s
- [ ] At least EVT000_1 through EVT000_5 have subtitles (these are the most dialogue-heavy FMVs)
- [ ] Test results documented in `docs/SUBTITLE_TEST_RESULTS.md`
