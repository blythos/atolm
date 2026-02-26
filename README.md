# Panzer Dragoon Saga Decompilation

A full decompilation and modern reimplementation of **Panzer Dragoon Saga** (Sega Saturn, 1998, Team Andromeda).

The goal is a native modern port: an application that loads the original disc image and runs the complete game on modern hardware — not emulation, but a true reimplementation of the game engine and logic.

## Status

**Phase 1: Asset Pipeline** — in progress. See [PROGRESS.md](docs/PROGRESS.md) for detailed status.

### What works today

| Category | Status |
|----------|--------|
| **3D Models** | ✅ All 351 MCB/CGB pairs extractable — dragons, characters, NPCs, enemies, bosses, fields |
| **Textures** | ✅ LUT (mode 1) and RGB555 (mode 5) fully decoded; bank-mode (0, 4) renders as greyscale pending PNB parser |
| **Skeleton & Animation** | ✅ Hierarchical poses and keyframe animation playback (4 animation modes) |
| **FMV Video** | ✅ All 14 CPK Cinepak videos extracted to MP4 with frame-accurate subtitles |
| **Sequenced Music** | ✅ 86 SEQ→MIDI conversions; 89 BIN tone banks→WAV instrument samples; official track names from SNDTEST.PRG |
| **PCM Audio** | ⬜ 270 PCM files on disc — extractor not yet started |
| **2D Assets** | ⬜ 163 SCB + 162 PNB files — parsers not yet started |
| **Fonts** | ⬜ FNT files — not yet started |
| **3D Viewer** | ✅ Browser-based Three.js viewer with textured models, animation playback, and asset browser |
| **Sound Test** | ✅ Browser-based MIDI playback + WAV auditioning with search and filtering |

## What This Is

This project converts the original SH-2 machine code and binary data formats into documented, readable source code. It builds on [yaz0r's Azel project](https://github.com/yaz0r/Azel) — an extraordinary MIT-licenced partial decompilation representing 5+ years of reverse engineering work.

Three reinforcing tracks:
- **Asset extraction** — parse every binary format (models, textures, audio, video, text)
- **Code decompilation** — convert SH-2 assembly to C/C++ for every game subsystem
- **Reimplementation** — modern engine (SDL2 + modern renderer) that runs the decompiled logic

## Legal

**This project does not contain any game data.** You must provide your own legally obtained copy of Panzer Dragoon Saga. The reimplementation loads the original disc image at runtime, the same way an emulator does.

Panzer Dragoon Saga is © SEGA. This is a clean-room style decompilation for interoperability and preservation purposes.

## Repository Structure

```
atolm/
├── docs/                           # Project documentation
│   ├── PROJECT_SCOPE.md            # Full scope, architecture, development phases
│   ├── PROGRESS.md                 # What's done, what's next
│   ├── TECHNICAL_REFERENCE.md      # Binary format specifications
│   ├── TOOL_CHAIN_AND_ROADMAP.md   # Tool inventory and path to playability
│   ├── QUICK_REFERENCE.md          # Cheat sheet for common operations
│   ├── SESSION_LOG.md              # Development history
│   └── cpk_format_research.md      # Sega FILM / CPK container format notes
│
├── tools/                          # Python extraction and analysis tools
│   ├── common/                     # Shared modules
│   │   ├── iso9660.py              #   ISO9660 disc image reader
│   │   └── saturn.py               #   Saturn hardware utilities
│   │
│   │  ── 3D Model Pipeline ──
│   ├── pds_extract.py              # MCB/CGB → JSON + texture atlas (main extractor)
│   ├── pds_extract_raw.py          # Raw binary MCB/CGB extraction
│   ├── mcb_extract.py              # MCB/CGB → glTF (.glb) export
│   │
│   │  ── 3D Viewer ──
│   ├── pds_viewer.html             # Browser-based model viewer (Three.js)
│   ├── viewer_renderer.js          # Viewer rendering engine
│   ├── viewer_animation.js         # Saturn animation state machine port
│   │
│   │  ── FMV / Subtitle Pipeline ──
│   ├── cpk_extract.py              # Sega FILM CPK → MP4 + WAV
│   ├── extract_subtitles.py        # PRG bytecode → SRT subtitles
│   ├── batch_process_FMVs.py       # Batch extract + subtitle + mux pipeline
│   │
│   │  ── Audio / Music ──
│   ├── seq_extract.py              # Extract SEQ/BIN files from disc
│   ├── seq_to_midi.py              # SEQ → MIDI converter
│   ├── ton_to_wav.py               # BIN tone bank → WAV instrument samples
│   ├── snd_split.py                # SEQ↔BIN pair catalogue (all 4 discs)
│   ├── build_sound_catalogue.py    # SNDTEST.PRG → official track names
│   ├── make_sf2.py                 # SoundFont (SF2) builder
│   ├── pcm_extract.py              # PCM audio extractor (WIP)
│   │
│   │  ── Sound Test ──
│   ├── sound_test_server.py        # HTTP server for browser sound test
│   ├── sound_test.html             # Browser-based sound test UI
│   │
│   │  ── Debug / Analysis ──
│   ├── debug/                      # Diagnostic and inspection scripts
│   │   ├── inspect_iso.py          #   List all files on a disc image
│   │   ├── audit_fmv_durations.py  #   Check subtitle/video sync
│   │   ├── compare_discs.py        #   Cross-disc file comparison
│   │   ├── inspect_movie_dat.py    #   Dump MOVIE.DAT contents
│   │   ├── inspect_movie_prg.py    #   Dump MOVIE.PRG contents
│   │   ├── inspect_verts.py        #   Vertex data inspector
│   │   ├── check_scale.py          #   Model scale validator
│   │   └── sim_mode4.py            #   Animation mode 4 simulator
│   └── investigate_bin.py          # BIN format investigation helper
│
├── tests/                          # Validation tests (planned)
├── output/                         # Extracted assets (gitignored)
├── ISOs/                           # Disc images (gitignored)
├── LICENSE                         # MIT
└── README.md                       # This file
```

## Getting Started

### Requirements
- Python 3.6+ (most tools use pure stdlib — no dependencies)
- [FFmpeg](https://ffmpeg.org/) for video muxing (`cpk_extract.py`, `batch_process_FMVs.py`)
- A modern browser with WebGL for the 3D viewer and sound test
- A Panzer Dragoon Saga disc image (raw Mode 2 track, `.bin` format)

### Extract 3D models
```bash
# Extract all models from Disc 1
python tools/pds_extract.py "path/to/disc1.bin" --extract-all -o output/

# Serve the viewer
cd output/
copy ..\tools\pds_viewer.html .
copy ..\tools\viewer_renderer.js .
copy ..\tools\viewer_animation.js .
python -m http.server 8080
# Open http://localhost:8080/pds_viewer.html
```

### Extract FMVs with subtitles
```bash
python tools/batch_process_FMVs.py "path/to/disc1.bin"
```

### Extract music
```bash
# Extract all SEQ/BIN files
python tools/seq_extract.py --iso "path/to/disc1.bin" --extract --output output/seq_extract/

# Convert a track to MIDI
python tools/seq_to_midi.py --input output/seq_extract/raw/KOGATA.SEQ --output output/midi/KOGATA.mid

# Extract instrument samples from a tone bank
python tools/ton_to_wav.py --input output/seq_extract/raw/KOGATA.BIN --output output/ton_wav/KOGATA/
```

See [tools/README.md](tools/README.md) for full documentation of all tools.

## Acknowledgements

- **yaz0r** — [Azel project](https://github.com/yaz0r/Azel). The foundation of this work. 468 commits and 76,000+ lines of decompiled PDS engine code, open-sourced under MIT licence.
- **Team Andromeda** — for creating one of the most remarkable games ever made.
- **The Panzer Dragoon community** — [Panzer Dragoon Legacy](https://www.panzerdragoonlegacy.com/), [Will of the Ancients](https://www.willoftheancients.com/) — decades of keeping the flame alive.

## Licence

MIT — see [LICENSE](LICENSE).
