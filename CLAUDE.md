# Panzer Dragoon Saga — Decompilation & Reengineering Project (CLAUDE.md)

This file is the persistent context document for Claude Code sessions. Read it in full at the start of every session. It supersedes any inconsistency in other docs.

---

## Project Goal

Full decompilation and native modern port of Panzer Dragoon Saga (Sega Saturn, 1998, Team Andromeda). The end deliverable is an application that loads the original disc image and runs the complete game on modern hardware — not emulation, a true reimplementation.

The working approach has three reinforcing tracks:
1. **Asset extraction** — parse every data format on disc into usable modern representations
2. **Code decompilation** — convert SH-2 machine code to readable C/C++
3. **Reimplementation** — build a modern engine that runs the decompiled logic with the original assets

Asset extraction is the validation layer: every format we crack proves our understanding of the code that processes it.

Primary disc: Panzer Dragoon Saga (USA) Disc 1, raw Mode 2 track image (`.bin`).

---

## Multi-Agent Workflow

**Claude (this session)** handles:
- Core pipeline: MCB/CGB parsing, skeletal transforms, texture decoding
- Format reverse engineering and binary analysis
- Architecture decisions, project documentation
- Any task touching established binary format assumptions

**Gemini via Antigravity** handles self-contained tasks defined in `TASK_*.md` files committed to the repo. Antigravity reads context from `.antigravity/rules.md` and `docs/`. It does not have session memory.

**Critical rule:** Never let Antigravity modify the core MCB/CGB parsing pipeline or skeletal transform math without Claude reviewing first. Antigravity has broken working implementations before by "fixing" things it didn't understand (see CPK audio incident in session history).

---

## Key Reference: yaz0r's Azel Project

Primary format reference: `github.com/yaz0r/Azel` — MIT-licensed partial C++ reimplementation of the PDS engine, 468 commits, 2015–2020, open-sourced February 2026.

Use it as a **spec reference**, not a dependency. Read the C++ to understand binary formats; write our own Python tools.

Key source paths:
- `AzelLib/processModel.h/cpp` — 3D model parsing, quad format, pointer patching
- `AzelLib/dragonData.cpp` — Dragon filename tables
- `AzelLib/field/` — Field area loading
- `AzelLib/3dEngine_textureCache.cpp` — VDP1 VRAM and texture management
- `AzelLib/kernel/fileBundle.h` — MCB bundle structure
- `AzelLib/kernel/animation.cpp` — Animation track stepping, bone transform accumulation
- `AzelLib/town/townScript.cpp` — PRG bytecode interpreter (opcodes for subtitles, FMV)
- `AzelLib/common.h` — s_MCB_CGB struct, dragon config tables

---

## Saturn Hardware Architecture

- **CPU**: Dual Hitachi SH-2 (32-bit RISC, **big-endian**)
- **VDP1**: Sprite/polygon processor — all 3D geometry as textured quads
- **VDP2**: Background/tilemap processor — 2D backgrounds, scroll planes
- **VDP1 VRAM**: 512KB at `0x25C00000–0x25C7FFFF`
- **VDP2 Color RAM**: Palette data used by both VDP1 and VDP2
- **All data is big-endian** — use `struct.unpack('>...')` everywhere

---

## Disc Image Format

Raw Mode 2 CD-ROM:
- 2352 bytes per sector: 16-byte header + 2048 bytes data + 288 bytes ECC
- Standard ISO9660 filesystem, PVD at sector 16
- Files are in a flat root directory (no subdirectories on Disc 1)

```python
SECTOR_SIZE = 2352
SECTOR_HEADER = 16
SECTOR_DATA = 2048

def read_sector(f, sector_num):
    f.seek(sector_num * SECTOR_SIZE)
    raw = f.read(SECTOR_SIZE)
    if len(raw) < SECTOR_SIZE:
        return b'\x00' * SECTOR_DATA
    return raw[SECTOR_HEADER:SECTOR_HEADER + SECTOR_DATA]

def read_file_from_disc(f, start_sector, size):
    data = bytearray()
    remaining = size
    sector = start_sector
    while remaining > 0:
        chunk = read_sector(f, sector)
        take = min(remaining, SECTOR_DATA)
        data.extend(chunk[:take])
        remaining -= take
        sector += 1
    return bytes(data)
```

ISO9660 parsing: PVD at sector 16, root directory record at PVD offset 156, parse directory entries (record length byte, then name, sector, size fields). Little-endian for ISO9660 metadata fields only; game data is big-endian.

---

## Binary Read Helpers (use these everywhere)

```python
import struct

def ru8(data, off):  return data[off]
def ru16(data, off): return struct.unpack_from('>H', data, off)[0]
def rs16(data, off): return struct.unpack_from('>h', data, off)[0]
def ru32(data, off): return struct.unpack_from('>I', data, off)[0]
def rs32(data, off): return struct.unpack_from('>i', data, off)[0]
```

---

## File Formats (Established)

### MCB — Model/Character Block

Self-contained binary bundle loaded to Work RAM. Contains all data needed to render a character or object.

**Structure:**
```
[pointer table: N × u32 big-endian offsets]
[sub-resources at those offsets]
```

The pointer table ends where the first pointed-to data begins. Find the table length by: start at offset 0, read u32 values, stop when one falls outside the file or lands before the current scan position.

**Sub-resource classification (auto-discovery heuristics — proven reliable):**

| Type | Detection |
|------|-----------|
| Model | `+0x04` is vertex count 1–5000; `+0x08` is valid offset with room for count×6 bytes |
| Hierarchy node | Three u32s all either 0 or valid offsets; first non-zero points to model-like data |
| Static pose data | N×36-byte blocks where scale fields (bytes 24–35) ≈ `0x10000` |
| Animation data | Typically 3–4KB, has flags/numBones/numFrames header structure |

**3D model sub-resource (at pointer table entry):**
```
+0x00  s32   radius (bounding sphere, 20.12 fixed-point)
+0x04  u32   numVertices
+0x08  u32   verticesOffset (relative to MCB file start)
+0x0C  ...   quads[] (terminated by 8 zero bytes for vertex indices)
```

**Vertex format:** 3 × s16 big-endian, **12.4 fixed-point** (divide raw value by 16 for float)

**Quad format (20 bytes base + lighting tail):**
```
+0x00  u16[4]  vertex indices A, B, C, D
              (if C == D, it's a degenerate triangle)
+0x08  u16     lightingControl  — bits 8–9: lighting mode
+0x0A  u16     CMDCTRL          — bits 4–5: texture flip H/V
+0x0C  u16     CMDPMOD          — bits 3–5: color mode; bit 6: SPD (transparency)
+0x0E  u16     CMDCOLR          — palette/LUT address
+0x10  u16     CMDSRCA          — texture source address
+0x12  u16     CMDSIZE          — bits 8–13: width÷8; bits 0–7: height
```

**Lighting tail bytes appended after each quad** (you MUST skip these or parsing goes out of sync):
```
Mode 0: +0 bytes
Mode 1: +8 bytes   (single normal: 3×s16 + 2 padding)
Mode 2: +48 bytes  (per-vertex normal + color)
Mode 3: +24 bytes  (per-vertex normal)
```

Extract lighting mode: `(lightingControl >> 8) & 3`

**Hierarchy node (12 bytes):**
```
+0x00  u32  modelOffset  (or 0)
+0x04  u32  childOffset  (or 0)
+0x08  u32  siblingOffset (or 0)
```

All offsets are relative to the MCB file start.

**Static pose data (36 bytes per bone):**
```
+0x00  s32[3]  translation XYZ   (16.16 fixed-point)
+0x0C  s32[3]  rotation XYZ      (16.16, where 0x10000 = 360°)
+0x18  s32[3]  scale XYZ         (16.16, rest pose = 0x10000 = 1.0)
```

Find the pose block by: count bones in the hierarchy tree (recursive walk), then search pointer table entries for a block of `numBones × 36` bytes where all scale fields (offset 24–35 in each 36-byte block) read approximately `0x10000`.

---

### CGB — Character Graphics Block

Raw VDP1 texture pixel data. No header. Loaded directly to VDP1 VRAM. Always paired 1:1 with an MCB by filename (`DRAGON0.MCB` → `DRAGON0.CGB`).

---

### Texture Addressing (Critical — Verified Across All Asset Types)

```python
texture_offset = cmdsrca * 8          # byte offset into CGB
palette_offset = cmdcolr * 8          # byte offset into CGB (LUT mode)
```

This has been verified on dragons, characters, NPCs, enemies, bosses, and field geometry (351 pairs). The VDP1 VRAM base offset and pointer-patching cancel exactly, leaving these simple formulas.

**Texture dimensions:**
```python
tex_w = (cmdsize & 0x3F00) >> 5       # width in pixels
tex_h = cmdsize & 0xFF                 # height in pixels
```

**Color modes** (from `(cmdpmod >> 3) & 7`):

| Mode | Format | Status |
|------|--------|--------|
| 0 | 4bpp bank — palette via VDP2 Color RAM | Renders greyscale (needs PNB) |
| 1 | 4bpp LUT — 16-color palette in CGB at `cmdcolr×8` | **Working** |
| 4 | 8bpp bank — 256-color via VDP2 Color RAM | Renders greyscale (needs PNB) |
| 5 | 16bpp direct RGB555 | **Working** |

**Saturn RGB555 decode:**
```python
def rgb555_to_rgba(word):
    r = ((word >> 0) & 0x1F) << 3
    g = ((word >> 5) & 0x1F) << 3
    b = ((word >> 10) & 0x1F) << 3
    msb = (word >> 15) & 1
    a = 0 if (msb == 0 and word != 0) else 255   # MSB=0, non-black = transparent
    return (r, g, b, a)
```

**4bpp LUT decode:**
```python
def decode_4bpp_lut(cgb, tex_offset, pal_offset, w, h, flip_h, flip_v):
    # Read 16-entry palette from CGB
    palette = []
    for i in range(16):
        word = ru16(cgb, pal_offset + i * 2)
        palette.append(rgb555_to_rgba(word))
    
    pixels = []
    for y in range(h):
        row = []
        for x in range(0, w, 2):
            byte = cgb[tex_offset + (y * w // 2) + (x // 2)]
            row.append(palette[(byte >> 4) & 0xF])
            row.append(palette[byte & 0xF])
        pixels.append(row)
    
    if flip_h: pixels = [row[::-1] for row in pixels]
    if flip_v: pixels = pixels[::-1]
    return pixels
```

---

### Coordinate System & Fixed-Point Arithmetic

The Saturn engine runs everything in **16.16 fixed-point** internally. Two source formats feed into it:

| Source | Format | Float conversion | In-engine (16.16) |
|--------|--------|------------------|--------------------|
| Vertex coordinates | 12.4 s16 | `raw / 16.0` | `raw × 4096` |
| Bone translations/rotations/scales | 16.16 s32 | `raw / 65536.0` | `raw` (already there) |

**For rendering/export**, unify both by dividing everything by 4096 after converting to 16.16:
```python
vertex_float = (raw_s16 * 4096) / 4096.0    # = raw_s16 / 1.0 ... 
# Simpler: keep vertices as raw_s16/16.0, keep translations as raw_s32/65536.0
# They ARE in the same proportional space — the /256 viewer convention works:
vertex_viewer = raw_s16 / 16.0
trans_viewer  = raw_s32 / 256.0    # NOT /65536 — scaled to match vertex space
```

**Why `/256` for translations (not `/65536`):** In the engine, 12.4 vertices get left-shifted by 4 before matrix multiply (to become 16.16). So vertex `raw=16` (=1.0 in 12.4) becomes `256` in 16.16. A bone translation of `256` in 16.16 should match. So to put translations on the same viewer scale as vertices: `raw_s32 / 256.0`. This was verified empirically in the Antigravity animation debugging session.

**Saturn angles:** `0x10000 = full circle (360°)`
```python
radians = (raw_s32 / 65536.0) * (2 * math.pi)
# Or for animation delta values (after stepAnimationTrack × 16 multiply):
# the result is directly in degrees
```

---

## Skeletal Transform Pipeline

This is the engine's exact traversal, reverse-engineered from `modeDrawFunction10Sub1` in yaz0r's Azel. Do not deviate.

```python
def walk_hierarchy(node_offset, mcb, pose_data, bone_index, matrix_stack):
    if node_offset == 0:
        return
    
    model_off = ru32(mcb, node_offset + 0)
    child_off  = ru32(mcb, node_offset + 4)
    sibling_off = ru32(mcb, node_offset + 8)
    
    bone = pose_data[bone_index]
    tx, ty, tz = [v / 256.0 for v in bone['translation']]   # 16.16 → viewer
    rx, ry, rz = [(v / 65536.0) * 2 * math.pi for v in bone['rotation']]
    sx, sy, sz = [v / 65536.0 for v in bone['scale']]
    
    # Push matrix
    m = matrix_stack[-1].copy()
    
    # Translate
    m = m @ translate_matrix(tx, ty, tz)
    
    # Rotate: ZYX order (Z first, then Y, then X)
    m = m @ rotate_z(rz)
    m = m @ rotate_y(ry)
    m = m @ rotate_x(rx)
    
    matrix_stack.append(m)
    
    # Draw model at this bone
    if model_off != 0:
        draw_model(model_off, mcb, m)
    
    # Recurse to children
    walk_hierarchy(child_off, mcb, pose_data, bone_index + 1, matrix_stack)
    
    # Pop
    matrix_stack.pop()
    
    # Continue to siblings (same bone index level)
    walk_hierarchy(sibling_off, mcb, pose_data, bone_index, matrix_stack)
```

**Rotation order is ZYX** (Z applied first, then Y, then X). This matches Saturn's hardware convention.

---

## Animation System

Animation data lives in the MCB pointer table (entries after pose data, typically 3–4KB each). Structure reverse-engineered from `AzelLib/kernel/animation.cpp`.

**Track format:** Each bone has separate tracks for translation X/Y/Z, rotation X/Y/Z, scale X/Y/Z. A track is a delta-encoded stream: the first frame stores a base value, subsequent frames store deltas.

**stepAnimationTrack** (yaz0r's key function): reads the delta for a bone/component at the current frame and returns `delta × 16`. The result is then accumulated into the current pose.

**Translation accumulation:**
```
current_translation += step_result  (in 16.16 FP space)
```

**Rotation accumulation:**
```
current_rotation += step_result  (in 16.16 FP space, 0x10000 = 360°)
```

The final viewer-space values use the same `/256` and `/65536` conventions as static pose data.

---

## Disc 1 Asset Survey

360 MCB files, 370 CGB files, 163 SCB, 162 PNB, 89 BIN, 59 PRG, 14 CPK, 270 PCM.

351 MCB/CGB pairs matched by filename.

**Naming conventions:**

| Pattern | Content |
|---------|---------|
| `DRAGON0–7` | 8 dragon base forms (Basic Wing → Solo Wing) |
| `DRAGONM1–7` | Dragon morph intermediate models |
| `DRAGONC0–7` | Dragon combat models |
| `C_DRA0–7` | Dragon collision meshes (MCB only, no CGB) |
| `RIDER0` | Edge riding pose (MCB only) |
| `EDGE`, `AZEL` | Main character battle models |
| `FLD_*` | Field exploration geometry (65 pairs, largest assets) |
| `*MP` / `*MP0–8` | Map/environment models (towns, interiors) |
| `X_A_*`, `X_E_*`, `X_F_*`, `X_G_*` | NPC models (Seekers' Stronghold) |
| `Z_A_*`, `Z_B_*`, `Z_E_*`, `Z_F_*` | NPC models (Zoah variants) |
| `BATTLE` | Battle system common assets |
| `COMMON3` | Shared 3D assets |
| `WORLDMAP` | World map model |
| Named enemies | `BEMOS`, `GRIGORIG`, `BARIOH`, `RAHAB`, `ANTIDRAG`, etc. |

**Known edge cases:**

- `*MP` files: Many standalone models, no hierarchy. Placed by PRG scene scripts. Currently extracted as unassembled parts at origin.
- Multi-hierarchy MCBs (GRIGORIG has 20, BEMOS has 7): Multiple model configs (battle phases, attack states). First hierarchy is the main/default form. All share the same pose data pool.
- MCBs without CGBs (C_DRA1–7, MDLCHG, RIDER0): Collision meshes or pose-only data.
- CGBs without MCBs (MENU, SAVE, TUTORIAL, etc.): 2D screen assets, use SCB/PNB system.

---

## Other File Formats

### CPK — Cinepak FMV Video

Sega FILM container (magic: `FILM`). Contains Cinepak-encoded video and PCM audio.

**Critical discoveries from extraction work:**
- Audio sample rate: **32000 Hz** (NOT in FDSC header — must be inferred from duration matching)
- Audio chunk detection requires content-aware heuristics (check if first 4 bytes of chunk match chunk size — if yes, video interframe; if no, audio PCM)
- Audio is 16-bit big-endian signed PCM, typically mono
- STAB entry field ordering in PDS files may differ from canonical Sega FILM spec

Working extractor: `tools/cpk_extract.py`

### PRG — SH-2 Executable Overlays

Bytecode scripts controlling scene logic, FMV playback, subtitle display. Interpreter reverse-engineered from `AzelLib/town/townScript.cpp`.

**Key subtitle opcodes:**
- `0x2E` — Frame sync (subtitle timing)
- `0x1B` — Draw string (subtitle on)
- `0x1D` — Clear string (subtitle off)
- `0x24` — Timed string (auto-clearing)
- `0x07` — FMV start (argument: CPK filename pointer)

String pointers use double indirection matching `readSaturnString()` in yaz0r's code. Text is plain null-terminated ASCII in the USA version.

Subtitle extraction: PRG bytecode walking for primary method; MOVIE.DAT group→CPK mapping as fallback.

### PCM — Audio Samples

270 files. Voice acting and SFX. Format under investigation (may be raw PCM or have a simple header).

### SEQ / BIN — Sequenced Music

SEQ files are MIDI-like sequence data (CyberSound "Saturn Sequence 2.00" format) paired with BIN tone banks (CyberSound TON format).

**TON/BIN format — fully reverse-engineered:**

File layout:
```
Bytes 0–7: four u16 BE section offsets: mixer_off, vl_off, peg_off, plfo_off
Bytes 8..(mixer_off−1): voice offset table — num_voices = (mixer_off − 8) / 2
[mixer / VL / PEG / PLFO sections — playback metadata, not needed for extraction]
Voice descriptors starting at plfo_off + 4:
  Each voice: 4-byte header (byte[2] = nlayers−1, signed) + nlayers × 32-byte layer blocks
```

Each 32-byte layer block:
```
+0x00  u16   LSA (loop start — for looped playback, not raw extraction)
+0x02  u32   bits[18:0] & 0x0007FFFF = tone_off (file-absolute byte offset to PCM data)
             byte[+3] bit 4 = PCM8B flag (1 = 8-bit, 0 = 16-bit)
+0x06  u16   LEA (loop end — use sample_count instead for extraction)
+0x08  u16   sample_count (in samples, not bytes)
+0x0A–0x1F   ADSR, volume, LFO, panning (runtime playback data)
```

**Critical:** `tone_off` is a direct file-absolute byte offset into the BIN file. No SCSP RAM base address adjustment needed. Sample rate is not encoded; default 22050 Hz.

Tools: `tools/seq_extract.py` (disc extraction + cataloguing), `tools/seq_to_midi.py` (SEQ→MIDI), `tools/ton_to_wav.py` (TON→WAV samples).

### SCB — Screen/Background Block

VDP2 tilemap data for 2D screens (menus, loading screens). Not yet parsed.

### PNB — Palette Block

VDP2 Color RAM data. Needed for bank-mode textures (modes 0 and 4). Not yet parsed. When available, `cmdcolr` for bank mode = palette bank index into PNB data.

---

## Tool Status

### Working
- ISO9660 filesystem reader (`tools/pds_raw_extract.py`) — reads raw Mode 2 track images
- MCB pointer table parser with auto-classification
- 3D model vertex/quad extraction with all 4 lighting modes
- Hierarchy tree walker with skeletal transforms
- Pose data finder (heuristic scale-field matching)
- Texture decoder: LUT mode (4bpp mode 1) and direct RGB (16bpp mode 5)
- OBJ+MTL+PNG textured export pipeline
- CPK video extraction (`tools/cpk_extract.py`) — MP4 output with working audio
- PRG subtitle extraction — SRT output, muxable into MP4
- 3D viewer (`tools/model_viewer/`) — Three.js, WebGL, orbit controls, animation playback
- SEQ disc extractor (`tools/seq_extract.py`) — catalogues and extracts all SEQ/BIN files
- SEQ→MIDI converter (`tools/seq_to_midi.py`) — full event parsing, multi-song support
- TON→WAV extractor (`tools/ton_to_wav.py`) — per-instrument WAV samples from BIN tone banks; verified across all 78 standalone BIN files on Disc 1

### Not Yet Implemented
- SND bundle splitter — EPISODE1–4 and INTER SND archives need unpacking at known offsets before their TON/SEQ banks can be processed
- PNB parser → bank-mode texture colours (modes 0, 4 currently greyscale)
- SCB parser (2D background tiles)
- PCM audio extraction (`tools/pcm_extract.py`) — 270 voice/SFX files, format TBD
- Animation keyframe decoder (full playback — partial work done)
- Multi-hierarchy scene assembly (field maps need PRG placement data)
- glTF export (preserves skeletal data better than OBJ)
- Batch extraction UI

---

## Repo Structure

```
/
├── CLAUDE.md                    ← this file
├── .antigravity/rules.md        ← Gemini/Antigravity context
├── docs/
│   ├── PROJECT_SCOPE.md
│   ├── PROJECT_INSTRUCTIONS.md
│   ├── TECHNICAL_REFERENCE.md
│   ├── QUICK_REFERENCE.md
│   └── PROGRESS.md
├── tools/
│   ├── pds_raw_extract.py       ← ISO9660 reader + MCB/CGB extractor
│   ├── cpk_extract.py           ← CPK/Cinepak FMV extractor
│   ├── model_viewer/            ← Three.js browser viewer
│   └── ...
├── TASK_*.md                    ← Antigravity task prompts
└── output/                      ← Extracted assets (gitignored)
```

Assets live outside the repo (copyright). Tools only. The extractor reads directly from the disc image at runtime.

---

## Development Principles

1. **Preserve Saturn binary formats** — Extract raw MCB/CGB/etc. files as-is. Decoders run at viewer/engine load time, not during extraction. This keeps the extraction layer simple and preserves data for decompilation.

2. **Separation of concerns** — Tools (distributable) vs. game assets (not distributable). No game data embedded in code or committed to the repo.

3. **Validate against yaz0r** — When uncertain about a format, read `yaz0r/Azel` first. Don't guess binary layouts.

4. **Big-endian everywhere** — Every struct.unpack uses `>`. No exceptions.

5. **Test against real data** — Run extraction against actual disc files and visually verify output before considering a format "understood".

6. **Coordinate with Claude before changing the pipeline** — The MCB/CGB/skeletal transform code represents accumulated session knowledge. Changes need context from this doc and previous session history.
