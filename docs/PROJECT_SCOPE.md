# Panzer Dragoon Saga: Project Scope & Architecture

## Mission

Full decompilation and modern reimplementation of Panzer Dragoon Saga (Sega Saturn, 1998, Team Andromeda). The goal is a native modern port that loads the original disc assets and runs the complete game — not an emulator, but a true reimplementation of the game engine and logic.

## Why This Matters

PDS is widely regarded as one of the greatest RPGs ever made, trapped on hardware that barely exists. Fewer than 30,000 copies were produced for Western markets. The original source code was reportedly lost. Saturn emulation works but is imperfect and inaccessible. This game deserves to be playable by anyone, on anything.

## Approach

### Decompilation (understanding the code)
Convert the original SH-2 machine code into readable, documented C/C++ that faithfully reproduces the game's behaviour. We build on yaz0r's Azel project (76,000 lines of partial decompilation, MIT licence) and extend it to full coverage.

### Asset Extraction (understanding the data)
Parse every binary format the game uses and export to modern equivalents. This is not separate from decompilation — it IS decompilation, viewed from the data side. Every format we crack validates our understanding of the code that processes it.

### Reimplementation (making it run)
Build a modern application (C++ with SDL2/modern rendering) that loads the original disc image, reads all assets using our documented parsers, and executes the decompiled game logic. The original disc remains the "ROM" — we don't redistribute any game data.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Modern Application                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │  Input    │  │  Audio   │  │ Renderer │  │  Save   │ │
│  │  (SDL2)   │  │  (SDL2)  │  │(Vulkan/  │  │ System  │ │
│  │          │  │          │  │  OpenGL)  │  │         │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬────┘ │
│       │              │             │              │       │
│  ┌────┴──────────────┴─────────────┴──────────────┴────┐ │
│  │              Decompiled Game Engine                   │ │
│  │  ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌──────────┐ │ │
│  │  │ Kernel  │ │ 3D Eng  │ │ Battle   │ │  Field   │ │ │
│  │  │ (boot,  │ │ (model  │ │ (combat, │ │ (explor, │ │ │
│  │  │ file I/O│ │ render, │ │ AI, RPG  │ │ scenes,  │ │ │
│  │  │ memory) │ │ camera) │ │ systems) │ │ scripts) │ │ │
│  │  └─────────┘ └─────────┘ └──────────┘ └──────────┘ │ │
│  │  ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌──────────┐ │ │
│  │  │  Menu   │ │  Town   │ │  Dragon  │ │  World   │ │ │
│  │  │ (UI,    │ │ (NPC,   │ │ (morph,  │ │   Map    │ │ │
│  │  │ invent) │ │ dialog) │ │ rider)   │ │          │ │ │
│  │  └─────────┘ └─────────┘ └──────────┘ └──────────┘ │ │
│  └──────────────────────┬──────────────────────────────┘ │
│                         │                                 │
│  ┌──────────────────────┴──────────────────────────────┐ │
│  │              Asset Pipeline (our parsers)             │ │
│  │  ISO9660 → MCB/CGB → Models, Textures               │ │
│  │            SCB/PNB → Backgrounds, Palettes           │ │
│  │            PCM/SEQ → Audio                           │ │
│  │            CPK     → Video                           │ │
│  │            PRG/EXB → (executed as decompiled code)   │ │
│  └──────────────────────┬──────────────────────────────┘ │
│                         │                                 │
│                   ┌─────┴─────┐                          │
│                   │ Disc Image│                          │
│                   │  (user    │                          │
│                   │ provides) │                          │
│                   └───────────┘                          │
└─────────────────────────────────────────────────────────┘
```

## The Code We Need to Decompile

### What exists on Disc 1:
| Component | Files | Total Size | Description |
|-----------|-------|-----------|-------------|
| Main kernel | 1ST_READ.PRG | 253 KB | Boot, file I/O, memory management, core engine |
| Scene overlays | 59 × .PRG | 15.3 MB | Field logic, battle scripts, town code, cutscenes |
| Extended data | 39 × .EXB | 52 KB | Supplementary executable data |
| **Total** | **99 files** | **~15.6 MB** | **All executable code** |

### What yaz0r has decompiled (Azel project):
| Subsystem | Lines | Coverage | Quality |
|-----------|-------|----------|---------|
| Battle system | 17,680 | Good — major battle logic decompiled | Working code with some stubs |
| Field system | 12,456 | Partial — FLD_A3 mostly done, others started | Mixed completeness |
| Town system | 8,531 | Partial | Working for some towns |
| Kernel / core | ~6,000 | Good — file I/O, memory, math, common functions | Solid foundation |
| 3D engine | ~3,000 | Good — model loading, rendering pipeline, transforms | Our asset extraction validates this |
| VDP1/VDP2 | ~2,500 | Partial — enough to render, not pixel-perfect | Functional |
| Menu system | 713 | Minimal — barely started | Stubs mostly |
| Audio | 922 | Minimal | Basic framework |
| **Total** | **~76,000** | **Roughly 30-40%** | **Runs some content** |

### What still needs decompiling:
- Most PRG overlays (each is a self-contained SH-2 program for a specific scene/battle/area)
- Menu, inventory, shop, save/load systems
- Dragon morphing stat calculations
- World map logic
- Most town interactions and NPC dialogue
- Cutscene scripting engine
- Audio driver (Motorola 68000 code for the SCSP sound processor)
- Remaining field areas and battle encounters

## Development Phases (Dependency-Ordered)

### Phase 1: Complete Asset Pipeline ← CURRENT
**Goal:** Parse every data format. Validate against real disc data.
**Why first:** Every subsequent phase needs reliable asset loading. Also directly produces decompiled format knowledge.

```
1.1  ✅ ISO9660 disc reader
1.2  ✅ MCB parser (pointer table, auto-classification)
1.3  ✅ 3D model extraction (vertices, quads, hierarchy, pose)
1.4  ✅ VDP1 texture decoder (LUT + RGB modes)
1.5  ✅ Textured OBJ export pipeline
1.6  PNB parser → bank-mode palette resolution
1.7  SCB parser → 2D backgrounds
1.8  Animation keyframe decoder
1.9  PCM audio extraction
1.10 SEQ music extraction
1.11 CPK video extraction
1.12 FNT font extraction
1.13 Text/string table extraction
1.14 Batch extraction tool with disc browser
```

### Phase 2: SH-2 Code Analysis Infrastructure
**Goal:** Build the tooling to systematically decompile PRG overlays.
**Why second:** Can't decompile code without disassembly and analysis tools.

```
2.1  SH-2 disassembler (or configure Ghidra with Saturn-specific annotations)
2.2  PRG overlay loader (understand how overlays are mapped into memory)
2.3  Cross-reference database (which functions call which, which data they touch)
2.4  VDP register annotation layer (label hardware register accesses)
2.5  Known-function signature library (from yaz0r's work — match patterns)
2.6  Automated decompilation assistance (Ghidra decompiler output → cleanup)
```

### Phase 3: Kernel & Core Engine Decompilation
**Goal:** Complete the engine foundation that all game logic depends on.
**Why third:** Game logic can't run without the kernel.
**Starting point:** yaz0r's existing kernel/3D engine code (~11K lines)

```
3.1  Complete file I/O system (all loading paths, streaming)
3.2  Complete memory management (allocation, overlay swapping)
3.3  Complete 3D engine (all rendering modes, effects, LOD)
3.4  Complete VDP1 command generation (all sprite/polygon types)
3.5  Complete VDP2 setup (all scroll plane configurations, rotation)
3.6  Math library (fixed-point, matrix, trig — partially done via COMMON.DAT)
3.7  Collision detection system
3.8  Camera system (all modes — battle, field, rail shooter, cutscene)
3.9  Input handling
3.10 Timer/interrupt handling
```

### Phase 4: Game Systems Decompilation
**Goal:** Decompile the RPG mechanics, UI, and system-level game logic.
**Why fourth:** These are the shared systems that every scene uses.

```
4.1  Dragon morphing system (stat calculation, form transitions)
4.2  Battle engine (turn order, damage formulas, berserk attacks, items)
4.3  Inventory / equipment system
4.4  Menu / UI system
4.5  Shop / trade system
4.6  Save / load system
4.7  World map (navigation, encounter triggers, area transitions)
4.8  Status effects, experience, leveling
4.9  Enemy AI framework
4.10 Dialogue / text display system
```

### Phase 5: Scene-by-Scene Decompilation
**Goal:** Decompile every PRG overlay — every field, battle, town, and cutscene.
**Why fifth:** This is the bulk of the work and depends on everything above.
**Strategy:** Work through the game linearly (Disc 1 Episode 1 → Disc 4 ending), decompiling each scene's overlay. Each completed scene can be tested.

```
5.1  Episode 1: Excavation Site (FLD_A3 series — partially done by yaz0r)
5.2  Episode 1: Battle encounters, bosses
5.3  Episode 2: Caravan, Georgius, Shelcoof sequence
5.4  Towns: Caravans, camps
5.5  Episode 3 onward (Disc 2-4 when we get those disc images)
...  (This phase contains the majority of the person-years of effort)
```

### Phase 6: Modern Renderer
**Goal:** Replace Saturn VDP1/VDP2 with a modern rendering backend.
**Why sixth:** Can develop in parallel with Phase 4-5, but needs engine decompilation (Phase 3) first.

```
6.1  Modern VDP1 equivalent (textured quad rendering via OpenGL/Vulkan)
6.2  Modern VDP2 equivalent (tilemap/scroll plane rendering)
6.3  Shader pipeline (lighting, fog, transparency matching Saturn behaviour)
6.4  Resolution-independent rendering (original was 320×224/352×224)
6.5  Optional: HD texture support (load high-res replacements)
6.6  Optional: widescreen support
```

### Phase 7: Audio Reimplementation
**Goal:** Faithfully reproduce the game's audio.
**Why seventh:** Can develop in parallel once the audio format is understood.

```
7.1  SCSP (Saturn sound processor) behaviour documentation
7.2  PCM sample playback engine
7.3  Sequenced music player (SEQ format)
7.4  Sound effect triggering (tied to game events)
7.5  CD audio track playback (red book audio)
7.6  Audio mixing and output (SDL2 audio)
```

### Phase 8: Integration & Testing
**Goal:** A complete, playable native port.

```
8.1  Full game playthrough testing (every scene, every battle, every dialogue)
8.2  Bug fixing and accuracy testing against Saturn emulator reference
8.3  Save compatibility
8.4  All 4 disc images supported
8.5  Platform builds (Windows, macOS, Linux)
8.6  Performance optimisation
8.7  Optional enhancements (configurable resolution, filtering, etc.)
```

### Phase 9: Saturn Generalisation & Release
**Goal:** Extract reusable Saturn tools, publish everything.

```
9.1  Factor out Saturn-generic libraries (ISO reader, VDP1/VDP2, SH-2 tools)
9.2  Test against Panzer Dragoon / Panzer Dragoon Zwei / Burning Rangers
9.3  Document the general Saturn RE toolkit API
9.4  Public release: tools, documentation, decompiled source (no game data)
9.5  Community handoff and maintenance
```

## Key Principles

1. **The disc image is the ROM.** We never distribute game data. The reimplementation loads the original disc, just like an emulator. Users must provide their own copy.

2. **Asset extraction validates decompilation.** Every format parser we write proves our understanding of the code that processes that format. The two efforts reinforce each other.

3. **yaz0r's Azel is our foundation, not our ceiling.** His 76K lines of MIT-licenced code are an enormous head start. We build on it, complete it, and credit it.

4. **Test continuously.** Each decompiled subsystem should be testable against the real game running in an emulator. Does our battle damage formula produce the same numbers? Does our model loader produce the same geometry? Byte-level accuracy is the standard.

5. **Work through the game linearly.** Decompiling scenes in gameplay order means each new scene builds on the systems already decompiled, and progress is measurable as "the game is playable up to this point."

6. **Document everything.** The decompilation itself is documentation. Every function gets a name, every constant gets explained, every data structure gets a comment. Future Saturn RE efforts benefit from this.

## What We Need Beyond Code

- **All 4 disc images** (Disc 1 is uploaded; Discs 2-4 needed eventually)
- **A Saturn emulator** for reference testing (Mednafen/Beetle Saturn recommended)
- **Ghidra with SH-2 support** for systematic PRG overlay decompilation
- **A C++ build environment** for the reimplementation (CMake + SDL2 + BGFX or similar)
- **Patience.** This is a marathon, not a sprint. The Phase 1-2 tooling is weeks of work. Phases 3-5 are months to years. But every step produces something useful and testable.
