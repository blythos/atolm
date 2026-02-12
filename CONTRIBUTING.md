# Contributing to PDS Decompilation

Thank you for your interest in helping bring Panzer Dragoon Saga back to the world. Here's how to get involved.

## What We Need Most

### SH-2 Reverse Engineering (Critical Path)
The biggest bottleneck is decompiling the ~15MB of SH-2 executable code across 59 PRG overlay files. Each overlay is a self-contained program for a specific game scene, battle, or area.

**How to help:**
- Pick an undecompiled PRG overlay
- Disassemble it (Ghidra with SH-2 processor module works well)
- Document the functions, name them, identify what they do
- Write equivalent C/C++ that produces the same behaviour
- Use yaz0r's Azel project as a reference for coding style and already-decompiled functions

### Saturn Hardware Expertise
If you know VDP1, VDP2, SCSP, or other Saturn hardware at a register level, we need accuracy reviews of our renderer and audio implementations.

### Testing
Run the reimplementation alongside a Saturn emulator (Mednafen recommended) and verify accuracy. Do battles produce the same damage numbers? Do models render identically? Does audio timing match?

### Asset Format Research
We still need parsers for: PNB (palette data), SCB (2D backgrounds), SEQ (sequenced music), and the animation keyframe format. If you enjoy binary format reverse engineering, these are well-scoped tasks.

## Guidelines

### Code Style
- Python tools: standard Python 3, type hints welcome, docstrings on public functions
- C++ reimplementation: follow yaz0r's Azel coding conventions for consistency
- All binary parsing: big-endian, document every offset, use named constants not magic numbers

### Commit Messages
- Prefix with the subsystem: `[asset]`, `[decomp]`, `[engine]`, `[docs]`, `[tools]`
- Be specific: `[decomp] Decompile FLD_A3 NPC interaction handler` not `update code`

### Documentation
- Every decompiled function gets a comment explaining what it does in game terms
- Every data structure gets field documentation
- Every magic number gets a named constant

### Legal
- **Never commit game data** (disc images, extracted assets, ROM dumps)
- **Never copy code from emulators** unless they're compatibly licenced
- yaz0r's Azel project is MIT-licenced, so building on it is fine with attribution
- When in doubt about clean-room requirements, ask

## Getting Set Up

1. Clone the repository
2. Install Python 3.8+ with Pillow and NumPy
3. Obtain your own copy of PDS (the disc image is not included)
4. For decompilation work: install Ghidra with the SH-2 processor module
5. For reimplementation work: CMake, SDL2, a C++17 compiler

## Communication

- Open an issue for bug reports, format discoveries, or decompilation questions
- Pull requests welcome for any contribution size
- If you're planning a large contribution (e.g. decompiling a whole PRG overlay), open an issue first to avoid duplicate work
