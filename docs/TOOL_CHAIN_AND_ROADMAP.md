# PDS Decompilation: Complete Tool Chain & Path to Playability

## The Three Levels of "Decompilation"

### Level 1: Asset Extraction (what we've been doing)
Extract all game data into modern formats. Produces a browsable archive of models, textures, audio, video, text. **Not playable** — just the raw materials.

### Level 2: Code Decompilation (what yaz0r's Azel project does)
Convert the SH-2 machine code back into readable C/C++ that reproduces the game's logic. PDS has ~15.3MB of executable code across 1ST_READ.PRG (253KB kernel), 59 PRG overlays (15.3MB scene/battle/field logic), and 39 EXB files (52KB). yaz0r's project has decompiled roughly 76,000 lines covering the 3D engine, battle system, some field logic, and core kernel — substantial but probably 30-40% of the full game.

### Level 3: Modern Port (playable on PC/modern hardware)
Use the decompiled code and extracted assets to build a native application. yaz0r's Azel project is actually *this* — it's a C++ reimplementation using SDL2 + BGFX (a cross-platform rendering library) that reads the original disc files and renders with OpenGL/Metal/Vulkan. It's a real port in progress, not just documentation.

---

## Complete Tool Inventory

### TIER 1: Asset Extraction Tools

| # | Tool | PDS-Specific? | Saturn-Generic? | Status |
|---|------|:---:|:---:|--------|
| 1 | **ISO9660 Disc Reader** | No | **Yes** — all Saturn games use this | ✅ Done |
| 2 | **MCB Parser** (pointer table, model/hierarchy/pose classification) | **PDS/Team Andromeda** — the bundle format is engine-specific | No | ✅ Done |
| 3 | **3D Model Extractor** (vertices, quads → OBJ/glTF) | Partially — the vertex/quad container is PDS-specific, but VDP1 quad command fields are Saturn-generic | Partially | ✅ Done |
| 4 | **VDP1 Texture Decoder** (4bpp LUT, 4bpp bank, 8bpp bank, 16bpp RGB) | No | **Yes** — these modes are Saturn hardware standard | ✅ LUT + RGB done, bank modes need PNB |
| 5 | **CGB Reader** (raw pixel data extraction) | **PDS** — headerless format with PDS-specific addressing | No | ✅ Done |
| 6 | **PNB Parser** (VDP2 Color RAM / palette tables) | Likely **PDS** — may have custom header structure | Partially — VDP2 CRAM format is Saturn-standard | ❌ Not started |
| 7 | **SCB Parser** (VDP2 tilemap/background data) | Likely **PDS** — custom container around Saturn-standard tile data | Partially | ❌ Not started |
| 8 | **Skeletal Pose/Animation Decoder** | **PDS** — the 36-byte bone format and animation track structure are engine-specific | No | ✅ Static pose done, keyframe animation not started |
| 9 | **PCM Audio Extractor** | Depends on format | Saturn SCSP audio format is generic | ❌ Not started |
| 10 | **SEQ Music Extractor** | Likely **PDS** — sequenced music format varies by game | No | ❌ Not started |
| 11 | **CPK Video Extractor** | No | **Yes** — Cinepak is a standard codec, Saturn CPK has a known container | ❌ Not started |
| 12 | **FNT Font Extractor** | Likely **PDS** | No | ❌ Not started |
| 13 | **Text/Script Extractor** | **PDS** — game text encoding and script format are game-specific | No | ❌ Not started |
| 14 | **Batch Extraction Tool** (disc browser + selective export) | Framework is generic, asset-type handlers are PDS-specific | Partially | ❌ Not started |

### TIER 2: Code Analysis Tools

| # | Tool | PDS-Specific? | Saturn-Generic? | Status |
|---|------|:---:|:---:|--------|
| 15 | **SH-2 Disassembler** | No | **Yes** — all Saturn games use SH-2 | ❌ Not started (Ghidra has SH-2 support) |
| 16 | **PRG Overlay Loader/Analyser** | **PDS** — the overlay loading mechanism is engine-specific | No | ❌ Not started |
| 17 | **Scene Script Decompiler** | **PDS** — the scripting system driving cutscenes, events, NPC placement is entirely game-specific | No | ❌ Not started |
| 18 | **Battle System Logic Analyser** | **PDS** | No | Partially covered by yaz0r (17,680 lines) |
| 19 | **Memory Map Documenter** | Partially — Saturn memory map is fixed, but game's usage of it is PDS-specific | Partially | ❌ Not started |

### TIER 3: Port/Reimplementation Tools

| # | Tool | PDS-Specific? | Saturn-Generic? | Status |
|---|------|:---:|:---:|--------|
| 20 | **VDP1 Software Renderer** (modern reimplementation) | No | **Yes** — renders Saturn VDP1 commands on modern GPU | Partially (yaz0r uses BGFX) |
| 21 | **VDP2 Background Renderer** | No | **Yes** — Saturn VDP2 scroll plane rendering | Partially (yaz0r has partial VDP2, 1953 lines) |
| 22 | **SCSP Sound Emulator** | No | **Yes** — Saturn sound processor | ❌ Not started (existing emulators have this) |
| 23 | **Game Engine Reimplementation** | **PDS** — the actual game logic, state machines, AI, RPG systems | No | Partially (yaz0r's 76K lines) |
| 24 | **Asset Pipeline** (load original disc assets at runtime for the port) | **PDS** | No | Partially (yaz0r's file loading works) |
| 25 | **Save System** | **PDS** | No | ❌ Not started |
| 26 | **Input/Controller Mapping** | Generic | **Yes** | Trivial with SDL2 |

---

## What's Saturn-Generic vs PDS-Specific: Summary

### Saturn-Generic (reusable across all Saturn games)
- ISO9660 disc reader
- VDP1 texture decoder (all 4 color modes)
- VDP1 polygon renderer
- VDP2 scroll plane renderer
- Saturn RGB555 color format
- SH-2 disassembly/analysis
- SCSP audio processing
- Cinepak (CPK) video decoding
- Fixed-point arithmetic utilities (12.4, 16.16, 20.12)
- Saturn memory map (hardware register locations)

### Team Andromeda-Specific (PDS, PD, PD Zwei, Burning Rangers)
- MCB/CGB bundle format
- Pointer table structure
- Skeletal hierarchy format (model/child/sibling 12-byte nodes)
- Static pose format (36 bytes/bone)
- Animation keyframe format
- Probably: SCB/PNB container structure

### PDS-Only
- Scene scripting system
- Battle system logic
- RPG mechanics (dragon morphing, stats, inventory)
- NPC dialogue/event system
- World map system
- Save file format
- Text encoding
- Most PRG overlay content

---

## Beyond PDS: Tools Needed for General Saturn Decompilation

Some things we'd want that aren't PDS-driven:

| Tool | Purpose | Notes |
|------|---------|-------|
| **SH-2 → C decompiler** | Automated decompilation of SH-2 binaries | Ghidra has basic SH-2 support; a Saturn-specific Ghidra plugin with VDP register annotations would be very valuable |
| **VDP1 command stream analyser** | Parse and visualise VDP1 command tables from any game | Saturn games all submit quads/sprites the same way |
| **VDP2 VRAM layout visualiser** | Show scroll plane tile maps, rotation coefficients, etc. | Useful for any 2D/background work |
| **Saturn executable loader** | Parse IP.BIN, 1ST_READ.BIN, understand the boot sequence | Standard across all Saturn games |
| **SMPC / peripheral decoder** | Controller input, RTC, region detection | Hardware standard |
| **CD block command analyser** | Understand disc access patterns, file streaming | Useful for understanding loading sequences |

Many of these exist in Saturn emulators (Mednafen, Kronos, SSF) but not as standalone RE tools.

---

## Path to "Playable on Modern Hardware"

### Option A: Complete yaz0r's Azel Project
yaz0r's project IS a modern port in progress. It uses SDL2 + BGFX for rendering, reads original disc files, and reimplements game logic in C++. The gap is:
- ~60-70% of game logic still needs decompiling (especially: most field areas, many battle scripts, menu systems, town interactions, cutscene scripting)
- VDP2 rendering is incomplete (backgrounds, some visual effects)
- Audio playback needs work
- Many PRG overlays (scene scripts) haven't been touched

**Effort:** Probably 2-4 person-years of skilled RE work to complete. This produces the highest-quality result — a true native port.

### Option B: Enhanced Emulation Wrapper
Instead of reimplementing the game logic, run the original SH-2 code in an emulator core but replace the hardware rendering with modern equivalents:
- Use an existing SH-2 CPU emulator (from Mednafen or similar)
- Replace VDP1 rendering with a modern GPU implementation (upscaled, filtered)
- Replace VDP2 with proper tilemap rendering
- Replace SCSP with modern audio output
- Add modern features: save states, widescreen, HD textures

**This is essentially what Saturn emulators already do.** The "tool" here would be a Saturn emulator with enhanced rendering. Projects like Kronos and Mednafen already exist. This doesn't require decompilation at all — just better emulation.

### Option C: Hybrid Approach (Most Practical)
Use extracted assets + partial decompilation + emulation:
1. **Extract all assets** (models, textures, audio, video, text) using our tools ← we're here
2. **Decompile the critical path**: the parts that interact with assets (model loading, rendering, scene setup) using yaz0r's work as a foundation
3. **Emulate the rest**: for complex game logic we haven't decompiled, run original SH-2 code in an interpreter, with hooks that redirect rendering to modern code
4. **Asset replacement pipeline**: load high-res replacement textures, re-exported models with higher poly counts, etc.

This is how many "HD remaster" projects work in practice.

### Option D: What We Can Actually Build With Our Tools
More realistically for a two-person effort, there are useful and achievable goals:

1. **Complete asset viewer/browser**: Load a PDS disc, browse all 3D models textured and posed, play audio, view FMVs. A "PDS Museum" application.

2. **Model replacement/mod tools**: Export models → edit in Blender → reimport. Combined with an emulator that supports texture/model replacement, this enables fan-made HD texture packs and model improvements.

3. **Translation tools**: Extract all game text, provide a framework for fan translations (PDS was only released in Japanese and English; fan communities have wanted other languages).

4. **Documentation**: Complete file format specifications that enable other developers to build tools. The PDS community (will-not-die.net, panzer dragoon legacy) would benefit enormously from this.

---

## Development Order (Dependencies Resolved)

### Phase 1: Complete Asset Extraction (current focus)
Dependencies: None (disc image only)
```
1.1  PNB parser (palettes)               → unblocks bank-mode textures
1.2  Bank-mode texture support            → depends on 1.1
1.3  SCB parser (2D backgrounds)          → depends on 1.1 for palettes
1.4  PCM audio extractor                  → independent
1.5  CPK video extractor                  → independent
1.6  FNT font extractor                   → independent
1.7  Animation keyframe decoder           → depends on existing pose infrastructure
```

### Phase 2: Batch Tool & Browser
Dependencies: Phase 1 tools
```
2.1  ISO9660 browser with file categorisation
2.2  Batch MCB/CGB extraction pipeline
2.3  Thumbnail/preview generation
2.4  Export format options (OBJ, glTF with skeleton, PNG atlas)
2.5  Command-line interface
2.6  Optional: simple GUI viewer
```

### Phase 3: Scene Understanding
Dependencies: Phase 1 + SH-2 analysis capability
```
3.1  PRG overlay analyser (SH-2 disassembly, likely via Ghidra integration)
3.2  Scene placement data extraction (model positions from scripts)
3.3  Field map assembly (combine models using placement data)
3.4  Camera path extraction
3.5  Lighting/fog parameter extraction
```

### Phase 4: Game Logic Decompilation
Dependencies: Phase 3 + yaz0r's Azel as reference
```
4.1  Continue yaz0r's decompilation of remaining PRG overlays
4.2  Battle system completion
4.3  Menu/inventory system
4.4  Dragon morphing system
4.5  NPC dialogue/event system
4.6  World map
```

### Phase 5: Modern Port
Dependencies: Phase 4 substantially complete
```
5.1  Modern VDP1 renderer (using extracted assets + decompiled draw calls)
5.2  Modern VDP2 renderer
5.3  Audio system (SCSP emulation or native audio)
5.4  Input system
5.5  Integration: load disc, run decompiled game logic, render with modern pipeline
5.6  Platform targets: Windows, macOS, Linux, (Switch homebrew?)
```

### Phase 6: Saturn Generalisation
Dependencies: Lessons learned from PDS
```
6.1  Factor out Saturn-generic libraries
6.2  Test against Panzer Dragoon / Panzer Dragoon Zwei
6.3  Document the Saturn-generic tool API
6.4  Public release with documentation
```

---

## Honest Assessment

Phases 1-2 are very achievable with our current approach and could be completed in weeks. Phase 3 is harder but tractable. Phases 4-5 are the "years of work" part — that's the actual game logic reimplementation. Phase 6 depends on how cleanly we factor things.

The most impactful deliverable for the PDS community would be a **complete Phase 2 tool** — a disc-to-assets extractor that handles all 351 model pairs, all audio, all video, all text, with a browsable interface. Nobody has released a comprehensive PDS asset extraction tool. Combined with the format documentation we've already produced, this would be genuinely useful and novel.

For "playable on modern hardware", the honest answer is that **Saturn emulators already make PDS playable** (Mednafen/Beetle Saturn runs it well). What doesn't exist is a *native port* — and that requires substantially completing the decompilation, which is the multi-year part. Our tools contribute to that goal by providing the asset pipeline and format documentation that any port effort would need.
