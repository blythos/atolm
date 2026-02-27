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

Bytecode scripts serving two roles: (1) FMV/cutscene control scripts (~50–100 KB) with subtitle opcodes and frame-sync commands, and (2) field area orchestration scripts (165–410 KB) containing NPC placement, scene logic, and serialized binary layout data (DataTable2/3, Grid1/2).

Interpreter reverse-engineered from `AzelLib/town/townScript.cpp`.

**Instruction format:** 1-byte opcode + operands. u8 args are byte-immediate; s16/u16 align to next even address; u32 align to next 4-byte address. String pointers use double indirection (Saturn RAM pointer -> null-terminated ASCII string). USA version text is plain ASCII.

**Complete opcode table:**

| Opcode | Name | Operands |
|--------|------|----------|
| 0x01 | end | none |
| 0x02 | wait | u16 frame_count |
| 0x03 | jump | u32 target_ea |
| 0x05 | if_false_jump | u32 target_ea |
| 0x06 | callScript | u32 target_ea |
| 0x07 | callNative | u8 num_args, u32 func_ea, [num_args x u32] |
| 0x08 | equal | s16 value |
| 0x09 | notEqual | s16 value |
| 0x0A | greater | s16 value |
| 0x0B | greaterEq | s16 value |
| 0x0C | less | s16 value |
| 0x0D | lessEq | s16 value |
| 0x0F | setBit | s16 bit_index |
| 0x11 | getBit | s16 bit_index |
| 0x12 | readPackedBits | s8 num_bits, s16 var_offset |
| 0x14 | addToPackedBits | s8 num_bits, s16 var_offset, s16 addend |
| 0x15 | switch | s8 arg, u8 num_cases, [num_cases x u32 jump_table] |
| 0x18 | setResult | none |
| 0x19 | addCinematicBars | none |
| 0x1A | removeCinematicBars | none |
| 0x1B | drawString | u32 string_ptr |
| 0x1D | clearString | none |
| 0x1F | waitNative | u8 num_args, u32 func_ea, [num_args x u32] |
| 0x20 | waitFade | none |
| 0x21 | playSystemSound | s8 sfx_id |
| 0x22 | playPCM | s8 pcm_file_index |
| 0x24 | displayTimedString | s16 duration, u32 string_ptr |
| 0x27 | multiChoice | s8 num_choices, [num_choices x u32 choice_ptrs] |
| 0x29 | getInventory | s16 item_index |
| 0x2B | addInventory | s8 count, s16 item_index |
| 0x2E | cutsceneFrameSync | s16 frame_number |
| 0x30 | receiveItem | s16 unk, s16 item_index, s16 count |

Note: game-state bit indices < 1000 have 3334 added automatically by the interpreter.

**Subtitle extraction:** PRG bytecode walking (primary); MOVIE.DAT group->CPK mapping (fallback). `tools/extract_subtitles.py` already implements all 30 opcodes.

**Field PRG binary data sections (FLD_*.PRG only):**

Field PRGs are ~85% bytecode + ~15% binary layout data past the final `0x01` (end) opcode. The `extract_subtitles.py` 0x2E-cluster heuristic does NOT work for field PRGs — a dedicated parser is needed.

- **DataTable3**: grid config header (0x24 bytes opaque + grid_width u32, grid_height u32, cell_size_x u32, cell_size_z u32 in 16.16 FP)
- **Grid1**: static geometry — entries of 0x18 bytes (u32 model_ref, u16[5] MCB offsets, s32[3] XYZ, s16[3] rotation, s16 flags); model_ref==0 terminates each cell
- **Grid2**: billboard/sprite instances — 0x10 bytes (u32 model_ref, s32[3] XYZ); model_ref==0 terminates
- **DataTable2**: NPC/object placement — 0x20 bytes (u32 entity_type_ptr, s32[3] XYZ, s16[3] rotation, s16 pad, s32 param, u32 model_ref); entity_type_ptr==0 terminates

All XYZ positions are 16.16 fixed-point; viewer divide by 256.

**Field area ID -> PRG mapping (from `AzelLib/common.cpp`):**

| Area | PRG | Subfields |
|------|-----|-----------|
| A0, D5 | FLD_D5.PRG | 1 |
| A2, A3 | FLD_A3.PRG | 13 (A3_0-A3_C) |
| A5 | FLD_A5.PRG | 13 (A5_0-A5_C) |
| A7 | FLD_A7.PRG | 3 |
| B1 | FLD_B1.PRG | 2 |
| B2, B3 | FLD_B2.PRG | 4 |
| B4, B5 | FLD_B5.PRG | 7 |
| B6 | FLD_B6.PRG | 10 |
| C2 | FLD_C2.PRG | 3 |
| C3, C4 | FLD_C4.PRG | 9 |
| C8, D4 | FLD_C8.PRG | 32 (largest: 410 KB) |
| D2 | FLD_D2.PRG | 2 |
| D3 | FLD_D3.PRG | 1 |

MCB/CGB pattern per area: `FLDCMN` + area base file + numbered subfields (e.g. FLD_A3_0 through FLD_A3_3 for A3).

**Other field file types:**
- **FNT** (12 on disc): per-character metrics for in-area UI
- **EPK** (E006.EPK etc.): interactive cutscene streaming containers (3D models + camera + audio) — NOT SEQ/TON audio bundles; format not yet decoded

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

**Critical:** `tone_off` is a direct file-absolute byte offset into the BIN file. No SCSP RAM base address adjustment needed.

**Sample rate** is encoded per-layer via OCT/FNS registers (MAME scsp.cpp formula):
```python
oct_signed = (oct_raw ^ 8) - 8       # 4-bit unsigned XOR 8 → signed −8..+7
sample_rate = int(44100 * (2 ** oct_signed) * (1 + fns / 1024))
sample_rate = max(1000, min(sample_rate, 96000))   # clamp for extremes
```

**Layer key range** (first two bytes of each 32-byte layer block):
```
+0x00  u8   lo_key   MIDI note lower bound (0 if full range)
+0x01  u8   hi_key   MIDI note upper bound (127 if full range)
```

**MIDI voice mapping:** MIDI program N → TON voice N. Each voice's layers define key-split zones. Voice index = program change value in SEQ data. This is 1:1 — 10 voices = 10 programs 0–9.

**SEQ multi-song file layout (CRITICAL — fixed bug here):**
```
[0:2]   u16  num_songs
[2:6]   u32  song_pointer[0]   ← ABSOLUTE byte offset to song[0]'s header
[6:10]  u32  song_pointer[1]   (if num_songs > 1)
...
```
Each song header at the pointed offset:
```
+0x00  u16  resolution        (MIDI ticks/beat — e.g. 48, 384, 480)
+0x02  u16  num_tempo_events
+0x04  u16  data_offset       (relative to song header start)
+0x06  u16  tempo_loop_offset
[num_tempo_events × 8 bytes: u32 tick + u32 microseconds_per_beat]
[sequence data at song_start + data_offset]
```

**CRITICAL BUG FIXED:** Old code read song pointers as 3-byte (`b'\x00' + data[2:5]`), giving ptr=0 for all files, making `resolution = num_songs` (1, 2, 3...) instead of the actual value (48, 480, 384). With resolution=1, all notes played in near-zero time. Fix: read as full 4-byte `struct.unpack('>I', data[2:6])[0]`.

Confirmed resolutions: TITLE.SEQ = 48, A3BGM = 48, CAMPBGM = 480, A3BOSS = 384, TOWNBGM = 48.

Tools: `tools/seq_extract.py` (disc extraction + cataloguing), `tools/seq_to_midi.py` (SEQ→MIDI), `tools/ton_to_wav.py` (TON→WAV samples), `tools/make_sf2.py` (BIN+WAVs→SF2 SoundFont).

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
- SEQ/BIN catalogue & extractor (`tools/snd_split.py`) — resolves all 86 SEQ->BIN pairs across all 4 discs (including 5 shared-bank cases), parses AREAMAP.SND, invokes ton_to_wav + seq_to_midi for batch conversion
- Sound catalogue builder (`tools/build_sound_catalogue.py`) — parses SNDTEST.PRG for 75 official track names; maps 57 to SEQ files on Disc 1; exposes 29 extra (SFX/battle) tracks for identification; outputs output/sound_catalogue.json
- Sound test browser engine (`tools/sound_test_server.py` + `tools/sound_test.html`) — Python HTTP server (stdlib only, port 8765); browser UI with MIDI playback via html-midi-player (GM soundfont), per-instrument WAV sample auditioning, search/filter, confidence badges; verification tool before SF2/pitch-data work

### Not Yet Implemented
- ~~SND bundle splitter~~ — **INVESTIGATED AND RESOLVED**: EPISODE1-4 and INTER SND files do NOT exist on any disc. The only .SND file is AREAMAP.SND (276 bytes, a runtime sound driver area-music command stream). All music is in standalone SEQ+BIN pairs, fully catalogued by snd_split.py.
- SEQ/BIN catalogue & extractor (`tools/snd_split.py`) — resolves all 86 SEQ→BIN pairs across all 4 discs (including 5 shared-bank cases), parses AREAMAP.SND, invokes ton_to_wav + seq_to_midi for batch conversion
- Sound catalogue builder (`tools/build_sound_catalogue.py`) — parses SNDTEST.PRG for 75 official track names; maps 57 to SEQ files on Disc 1; exposes 29 extra (SFX/battle) tracks for identification; outputs output/sound_catalogue.json
- SF2 SoundFont builder (`tools/make_sf2.py`) — converts BIN tone banks + extracted WAVs into standard SF2 2.01 files; no external libraries required; maps voice N → MIDI program N with correct key-split zones and per-sample OCT/FNS pitch rates; batch-converts all 84 disc1 banks to `output/sf2/` (16.2 MB total)
- Sound test browser engine (`tools/sound_test_server.py` + `tools/sound_test.html`) — Python HTTP server (stdlib only, port 8765); custom Tone.js MIDI player using Saturn WAV samples as instruments (correct timbres, no GM soundfont); in-browser MIDI binary parser; Web Audio API waveform/spectrum visualiser; volume slider; pitch shift for WAV preview; progress bar with elapsed/total time; search/filter; confidence badges

### Not Yet Implemented
- ~~SND bundle splitter~~ — **INVESTIGATED AND RESOLVED**: EPISODE1–4 and INTER SND files do NOT exist on any disc. The only .SND file is AREAMAP.SND (276 bytes, a runtime sound driver area-music command stream). All music is in standalone SEQ+BIN pairs, fully catalogued by snd_split.py.
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
