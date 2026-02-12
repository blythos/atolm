# Panzer Dragoon Saga Decompilation

A full decompilation and modern reimplementation of **Panzer Dragoon Saga** (Sega Saturn, 1998, Team Andromeda).

The goal is a native modern port: an application that loads the original disc image and runs the complete game on modern hardware — not emulation, but a true reimplementation of the game engine and logic.

## Status

**Phase 1: Asset Pipeline** — in progress

We can currently extract textured 3D models from the game disc, including:
- All 8 dragon forms with correct skeletal poses and textures
- Player characters (Edge, Azel)
- NPCs with full bone hierarchies
- Enemies and bosses
- Field/environment geometry

See [PROGRESS.md](docs/PROGRESS.md) for detailed status.

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
pds-decompilation/
├── docs/                    # Project documentation
│   ├── PROJECT_SCOPE.md     # Full scope, architecture, and development phases
│   ├── PROGRESS.md          # What's done, what's next
│   ├── TECHNICAL_REFERENCE.md  # Binary format specifications
│   ├── SESSION_LOG.md       # Development history
│   └── QUICK_REFERENCE.md   # Cheat sheet for common operations
├── tools/                   # Python extraction and analysis tools
│   ├── iso_reader.py        # ISO9660 filesystem reader for Saturn discs
│   ├── mcb_parser.py        # MCB bundle parser with auto-classification
│   ├── cgb_decoder.py       # CGB/VDP1 texture decoder
│   ├── model_exporter.py    # Textured OBJ/glTF export pipeline
│   └── batch_extract.py     # Disc browser and batch extraction (planned)
├── src/                     # C++ reimplementation (future)
│   ├── engine/              # Core engine (3D, file I/O, math)
│   ├── game/                # Game logic (battle, field, menu, dragon)
│   ├── renderer/            # Modern VDP1/VDP2 replacement
│   └── audio/               # Sound system
├── tests/                   # Validation against known-good output
├── LICENSE                  # MIT
├── README.md                # This file
└── CONTRIBUTING.md          # How to help
```

## Getting Started

### Requirements
- Python 3.8+
- Pillow (PIL) for image processing
- NumPy for matrix operations
- A Panzer Dragoon Saga disc image (raw Mode 2 track, .bin format)

### Extract a model
```bash
# Coming soon — batch extraction tool
# For now, see tools/ for individual extraction scripts
python tools/model_exporter.py --disc path/to/disc1.bin --asset DRAGON0 --output dragon0/
```

## Acknowledgements

- **yaz0r** — [Azel project](https://github.com/yaz0r/Azel). The foundation of this work. 468 commits and 76,000+ lines of decompiled PDS engine code, open-sourced under MIT licence.
- **Team Andromeda** — for creating one of the most remarkable games ever made.
- **The Panzer Dragoon community** — [Panzer Dragoon Legacy](https://www.panzerdragoonlegacy.com/), [Will of the Ancients](https://www.willoftheancients.com/) — decades of keeping the flame alive.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The project needs:
- **SH-2 reverse engineers** — decompiling PRG overlays is the critical path
- **Saturn hardware experts** — VDP1/VDP2 accuracy, SCSP audio
- **C++ developers** — for the reimplementation engine
- **Testers** — comparing output against emulator reference runs
- **Translators** — PDS was only released in English and Japanese

## Licence

MIT — see [LICENSE](LICENSE).
