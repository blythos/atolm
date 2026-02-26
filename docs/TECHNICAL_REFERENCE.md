# Technical Reference: PDS Binary Formats & Saturn Hardware

## Fixed-Point Arithmetic

The Saturn SH-2 has no FPU. All "floating point" values are fixed-point integers.

| Format | Type | Raw → Float | Float → Raw | Usage |
|--------|------|-------------|-------------|-------|
| 12.4 | s16 | raw / 16.0 | float × 16 | Vertex coordinates |
| 16.16 | s32 | raw / 65536.0 | float × 65536 | Bone translations, scales |
| 20.12 | s32 | raw / 4096.0 | float × 4096 | Bounding radii |

**Coordinate space unification for export:**
The engine internally converts 12.4 vertices to 16.16 via `raw_s16 × 16` (shift left 4 bits). For OBJ output, we unify by working in 16.16 space then dividing by 4096:
```python
vertex_float = raw_s16 * 16 / 4096.0  # = raw_s16 / 256.0
bone_translation_float = raw_s32 / 4096.0  # raw is already 16.16, /4096 for scale
```

## Saturn Angle System

Full circle = 0x10000 (65536) units.
```python
radians = raw_s32 / 65536.0 * 2 * math.pi
degrees = raw_s32 / 65536.0 * 360.0
```

## Rotation Matrix (ZYX Euler Order)

The engine applies rotations as Z first, then Y, then X. From yaz0r's `rotateCurrentMatrixZYX`:
```python
def rot_zyx(rx, ry, rz):
    cx, sx = cos(rx), sin(rx)
    cy, sy = cos(ry), sin(ry)
    cz, sz = cos(rz), sin(rz)
    # Row-major matrix:
    m[0][0] = cy*cz;          m[0][1] = cy*sz;          m[0][2] = -sy
    m[1][0] = sx*sy*cz-cx*sz; m[1][1] = sx*sy*sz+cx*cz; m[1][2] = sx*cy
    m[2][0] = cx*sy*cz+sx*sz; m[2][1] = cx*sy*sz-sx*cz; m[2][2] = cx*cy
```

## Hierarchy Traversal (Engine Match)

From yaz0r's `modeDrawFunction10Sub1`:
```
do {
    pushMatrix()
    translateCurrentMatrix(bone.translation)
    rotateCurrentMatrixZYX(bone.rotation)
    draw(model_at_node)          // vertices transformed by accumulated matrix
    if (child) {
        advance_bone_index()
        recurse(child)            // children inherit parent transform
    }
    popMatrix()                   // restore parent's parent transform
    if (!sibling) break
    advance_bone_index()
    node = sibling                // siblings share same parent transform
} while(true)
```

**Bone counting** (recursive): `count(node) = 1 + count(child) + count(sibling)`

## VDP1 Command Table Fields

These map directly to Saturn hardware registers. Each quad in the MCB stores a subset.

| Field | Bits | Meaning |
|-------|------|---------|
| CMDCTRL bit 4 | H-flip | Mirror texture horizontally |
| CMDCTRL bit 5 | V-flip | Mirror texture vertically |
| CMDPMOD bits 3-5 | Color mode | 0=4bpp bank, 1=4bpp LUT, 4=8bpp bank, 5=16bpp RGB |
| CMDPMOD bit 6 | SPD | Sprite Pixel Disable (when set, pixel 0 is opaque not transparent) |
| CMDCOLR | Palette ref | ×8 for LUT address, ×2 for bank address |
| CMDSRCA | Texture ref | ×8 for texture byte address in VDP1 VRAM |
| CMDSIZE[13:8] | Width÷8 | `(CMDSIZE & 0x3F00) >> 5` gives pixel width |
| CMDSIZE[7:0] | Height | `CMDSIZE & 0xFF` gives pixel height |

## Saturn RGB555 Color Format

```
Bit 15: MSB (shadow/priority flag — set means valid color for LUT entries)
Bits 14-10: Blue (5 bits)
Bits 9-5: Green (5 bits)  
Bits 4-0: Red (5 bits)

To RGBA8888:
  R = (color & 0x1F) << 3
  G = ((color >> 5) & 0x1F) << 3
  B = ((color >> 10) & 0x1F) << 3
```

## Texture Addressing

**Critical finding (verified across all asset categories):**
```
CGB_byte_offset = CMDSRCA_raw × 8
Palette_byte_offset = CMDCOLR_raw × 8  (for LUT mode)
```

The VDP1 offset patching and VRAM base address cancel exactly. No per-file offset knowledge is needed.

## MCB Pointer Table Entry Classification

Heuristic rules for auto-discovery (all verified working):

**Model:** `entry[+4]` is vertex count (1-5000), `entry[+8]` is valid offset with room for count×6 bytes
```python
nv = read_u32(data, off + 4)
vo = read_u32(data, off + 8)
is_model = (0 < nv < 5000) and (0 < vo < len(data)) and (vo + nv * 6 <= len(data))
```

**Hierarchy:** Three u32s that are all 0 or valid offsets, first (if non-zero) points to model data
```python
m, c, s = read_u32(data, off), read_u32(data, off+4), read_u32(data, off+8)
all_valid = all(v == 0 or (0 < v < len(data)) for v in [m, c, s])
first_is_model = m > 0 and looks_like_model(data, m)
```

**Static pose:** N×36 byte blocks where bytes 24-35 (scale fields) are all near 0x10000
```python
for bone in range(num_bones):
    sx = read_s32(data, off + bone*36 + 24)
    sy = read_s32(data, off + bone*36 + 28)  
    sz = read_s32(data, off + bone*36 + 32)
    assert all(abs(v - 0x10000) < 0x8000 for v in [sx, sy, sz])
```

## Dragon Filename Table (from yaz0r)

| Level | Name | Base MCB/CGB | Morph MCB/CGB | Combat MCB/CGB |
|-------|------|-------------|---------------|----------------|
| 0 | Basic Wing | DRAGON0 | — | DRAGONC0 |
| 1 | Valiant Wing | DRAGON1 | DRAGONM1 | DRAGONC1 |
| 2 | Stripe Wing | DRAGON2 | DRAGONM2 | DRAGONC2 |
| 3 | Panzer Wing | DRAGON3 | DRAGONM3 | DRAGONC3 |
| 4 | Eye Wing | DRAGON4 | DRAGONM4 | DRAGONC4 |
| 5 | Arm Wing | DRAGON5 | DRAGONM5 | — |
| 6 | Light Wing | DRAGON6 | — | — |
| 7 | Solo Wing | DRAGON7 | DRAGONM7 | — |

## VDP1 Quad UV Mapping

Saturn VDP1 maps texture corners to quad vertices in fixed order:
- Vertex A → UV (0, 0) — top-left
- Vertex B → UV (1, 0) — top-right  
- Vertex C → UV (1, 1) — bottom-right
- Vertex D → UV (0, 1) — bottom-left

Saturn V=0 is top of texture. OBJ V=0 is bottom. Flip: `obj_v = 1.0 - saturn_v`

H-flip and V-flip from CMDCTRL swap the U or V range respectively.

Degenerate quads (C == D) are triangles — emit as single triangle in OBJ.

## ISO9660 Sector Reading

Saturn disc images use Mode 2 sectors:
```python
SECTOR_SIZE = 2352
HEADER_SIZE = 16    # sync + header
DATA_SIZE = 2048    # user data
# ECC_SIZE = 288    # error correction (ignored)

def read_sector(f, sector_num):
    f.seek(sector_num * SECTOR_SIZE)
    raw = f.read(SECTOR_SIZE)
    return raw[HEADER_SIZE : HEADER_SIZE + DATA_SIZE]
```

Primary Volume Descriptor at sector 16. Root directory entry at PVD offset 156.

## PCM Audio Sample Format

Standalone `.PCM` files on the disc (outside of CPK containers) are typically raw audio data with no header.

**Format:**
- **16-bit**: Big-Endian Signed Integer (`>i2`). This is different from WAV (Little-Endian).
- **8-bit**: Signed Integer (`int8`). This is different from WAV (Unsigned `uint8`).
- **Sample Rate**: Often 22050 Hz (common for SFX), but can vary (11025, 16000, 32000).
- **Channels**: Typically Mono.

**Conversion to WAV:**
1. **16-bit**: Byte-swap to Little-Endian.
2. **8-bit**: Convert Signed to Unsigned (`u8 = s8 + 128`).

---

## CyberSound TON Format (Instrument Sample Banks)

In-game music uses Sega's **CyberSound** system running on the SCSP chip's embedded Motorola 68EC000 CPU. Small SEQ sequence files drive playback; the actual PCM waveforms live in TON-format banks. In PDS these banks are stored as `.BIN` files paired with `.SEQ` files by the same base name.

### File Structure

```
Bytes 0–1:  mixer_off  (u16 BE) — byte offset to mixer section
Bytes 2–3:  vl_off     (u16 BE) — byte offset to VL (volume/level) section
Bytes 4–5:  peg_off    (u16 BE) — byte offset to PEG (pitch envelope) section
Bytes 6–7:  plfo_off   (u16 BE) — byte offset to PLFO (pitch LFO) section

Bytes 8..(mixer_off−1): Voice offset table
  num_voices = (mixer_off − 8) / 2
  Each entry: u16 BE byte offset to that voice's descriptor block

[mixer section]   — SCSP mixer data, not needed for extraction
[vl section]      — per-voice volume data
[peg section]     — pitch envelope generator data
[plfo section]    — always 4 bytes

Voice descriptors (starting at plfo_off + 4, laid out sequentially):
  Each voice: [4-byte header] + [nlayers × 32-byte layer blocks]
  Header byte[2] = nlayers − 1  (signed; 0 means 1 layer, 2 means 3 layers, etc.)

PCM sample data: embedded inline within the file; accessed via tone_off pointers.
```

### Layer Block (32 bytes per layer)

```
+0x00–0x01  LSA    loop start address (not needed for WAV export)
+0x02–0x05  u32 BE:
              bits[18:0] & 0x0007FFFF = tone_off  (file-absolute byte offset to PCM data)
              byte[+0x03] bit 4        = PCM8B flag (1 = 8-bit PCM, 0 = 16-bit PCM)
+0x06–0x07  LEA    loop end address (not used — sample_count is authoritative for length)
+0x08–0x09  u16 BE = sample_count  (in samples, not bytes)
+0x0A–0x1F  ADSR, volume, LFO, panning — not needed for raw sample extraction
```

### Key Facts

- **tone_off is file-absolute** — it is a direct byte offset into the BIN file, not a SCSP RAM address. No separate "PCM start" calculation is needed.
- **Multiple voices can share the same tone_off** — deduplication by `(tone_off, sample_count, pcm8b)` is required.
- **Sample rate** is not encoded per-sample in the BIN file. Default to **22050 Hz**. The SCSP sequencer adjusts pitch at runtime via OCT/FNS registers on a per-note basis; these are not base sample rates.
- **Out-of-bounds tone_off values** occur in some BIN files (e.g. BOS5BGM.BIN) that reference PCM data expected to be pre-loaded into SCSP RAM by a companion bank. These are not SND bundle cross-references — SND bundles do not exist on PDS discs. Skip gracefully.
- **8-bit signed PCM** must be converted to unsigned for WAV: `wav_byte = pcm_byte + 128`.
- **16-bit PCM** is big-endian signed; must be byte-swapped to little-endian for WAV.

### AREAMAP.SND — Area Music Command Stream

The only `.SND` file on any PDS disc is `AREAMAP.SND` (276 bytes). It is **not** a container
archive. The sound driver (SDDRVS.TSK, running on the SCSP's 68000) loads it to Work RAM at
offset `sat_ram + 0x0A000` and uses it as a command stream to select which SEQ and TON banks to
queue for each in-game area.

The `EPISODE1–4.SND` and `INTER12/23/35.SND` bundles described in some community documentation
**do not appear in the ISO9660 filesystem on any of the four PDS USA discs**. All music is in
86 standalone `.SEQ` files paired with 89 `.BIN` tone banks (5 SEQ files share a bank).

Tool: `tools/snd_split.py` — parses AREAMAP.SND and catalogues all SEQ->BIN pairs across all
four discs with correct shared-bank resolution.

### Tool

`tools/ton_to_wav.py` — extracts all unique PCM samples from a standalone BIN tone bank to individual WAV files.

```bash
python tools/ton_to_wav.py --input output/seq_extract/raw/KOGATA.BIN --output output/ton_wav_test/KOGATA/
```

### SNDTEST.PRG — Official Track Name Table

Hidden sound test overlay on Disc 1 (5,644 bytes). Contains the only official track labels
in the game: 75 fixed-width (12-char) ASCII strings between the sentinel `COMMON` and the
hard terminator `ERR_STOP`.

```
COMMON         <- sentinel marking start of name table
A3 1 1 (MAP)   <- track 0
A3 1 2 (MAP)   <- track 1
...
TITLE
DROGON 00
EDGE
ERR_STOP       <- hard terminator (not a track name)
```

Of the 86 SEQ files on Disc 1, 57 are mapped to SNDTEST names. The remaining 29 are sound
effect banks, battle music, and utility tracks not exposed in the sound test; these are
accessible in the sound test browser under "Extra Tracks" for identification.

18 SNDTEST names have no matching SEQ on Disc 1 (A7 BOSS, B1/B3 tracks, C5 tracks, D5 boss,
EVENT 06, EVENT 11, DROGON 08, EDGE2) — these likely reside on Discs 2–4.

**Tools:**
```bash
# Build the mapping (SNDTEST.PRG names -> SEQ/BIN/MIDI/WAV paths):
python tools/build_sound_catalogue.py --sndtest output/seq_extract/SNDTEST.PRG
# Output: output/sound_catalogue.json

# Start the browser sound test UI:
python tools/sound_test_server.py
# Open: http://localhost:8765/
```

---

## PRG Bytecode Overlays

PRG files serve two roles: (1) FMV/cutscene control scripts (~50–100 KB) containing subtitle
opcodes and frame-sync commands, and (2) field area orchestration scripts (165–410 KB) containing
NPC placement, scene logic, and serialized binary layout data.

### Instruction format

- 1-byte opcode, followed by operands
- **Alignment**: u8 args are byte-immediate; s16/u16 args align to the next even address after
  the opcode byte; u32 args align to the next 4-byte address
- **String pointers**: u32 pointer to a Saturn RAM address that itself points to a
  null-terminated ASCII string (double indirection). USA version text is plain ASCII.
- **Base address detection**: scan the first 0x2000 bytes for u32 values in the Work RAM High
  range (0x06000000–0x060FFFFF); the most common 64 KB-aligned value is the load base.

### Complete opcode table (from `AzelLib/town/townScript.cpp`)

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

### Field PRG binary data sections (FLD_*.PRG only)

Field PRG files are ~85% bytecode and ~15% serialized binary data at the end of file. The data
sections begin past the final `0x01` (end) opcode. The bytecode region can be identified by
scanning for runs of zero-padding that signal the boundary. **The existing `extract_subtitles.py`
heuristic (hunting for 0x2E clusters) does not work for field PRGs** — a dedicated field data
parser is needed.

**DataTable3** — grid metadata header (0x24 bytes opaque config + fields):
```
+0x00-0x23  u8[0x24]  config (partially decoded — area type flags, camera bounds, etc.)
+0x24       u32       grid_width   (number of cell columns)
+0x28       u32       grid_height  (number of cell rows)
+0x2C       u32       cell_size_x  (16.16 fixed-point, world units per cell X)
+0x30       u32       cell_size_z  (16.16 fixed-point, world units per cell Z)
```
Followed immediately by pointers to Grid1, Grid2, and camera visibility arrays.

**Grid1** — static environment geometry per grid cell (0x18 bytes per entry):
```
+0x00  u32      model_ref   (0 = null terminator/end of cell)
+0x04  u16[5]   model_offsets_within_MCB
+0x08  s32[3]   position XYZ  (16.16 fixed-point; viewer: divide by 256)
+0x14  s16[3]   rotation XYZ  (12.4 fixed-point)
+0x1A  s16      flags
```
Each grid cell is a null-terminated array (model_ref == 0 marks end).

**Grid2** — billboard/sprite instances per cell (0x10 bytes per entry):
```
+0x00  u32      model_ref   (0 = null terminator)
+0x04  s32[3]   position XYZ  (16.16 fixed-point)
```

**DataTable2** — NPC/interactive object placement (0x20 bytes per entry):
```
+0x00  u32      entity_type_ptr  (0 = null terminator)
+0x04  s32[3]   position XYZ    (16.16 fixed-point)
+0x10  s16[3]   rotation XYZ    (12.4 fixed-point)
+0x16  s16      padding
+0x18  s32      parameter
+0x1C  u32      model_ref
```

**Camera visibility table** — 2-byte entries `(s8 camera_id, s8 unused)`, terminated by
`camera_id == -1`.

### Field area ID -> PRG file mapping (from `AzelLib/common.cpp`)

| Area ID | PRG file | Subfields | Notes |
|---------|----------|-----------|-------|
| A0 | FLD_D5.PRG | 1 | World map intro |
| A2 | FLD_A3.PRG | 1 | |
| A3 | FLD_A3.PRG | 13 (A3_0-A3_C) | |
| A5 | FLD_A5.PRG | 13 (A5_0-A5_C) | |
| A7 | FLD_A7.PRG | 3 (A7_0-A7_2) | |
| B1 | FLD_B1.PRG | 2 (B1_0-B1_1) | |
| B2 | FLD_B2.PRG | 4 (B2_1, B2_3-B2_5) | |
| B3 | FLD_B2.PRG | 1 | Shares PRG with B2 |
| B4 | FLD_B5.PRG | 1 | Demo only |
| B5 | FLD_B5.PRG | 7 (B5_0-B5_6) | |
| B6 | FLD_B6.PRG | 10 (B6_0-B6_9) | |
| C2 | FLD_C2.PRG | 3 (C2_0-C2_2) | |
| C3 | FLD_C4.PRG | 1 | Demo only |
| C4 | FLD_C4.PRG | 9 (C4_0-C4_8) | |
| C8 | FLD_C8.PRG | 32 | Tower interior (largest PRG: 410 KB) |
| D2 | FLD_D2.PRG | 2 (D2_0-D2_1) | |
| D3 | FLD_D3.PRG | 1 | |
| D4 | FLD_C8.PRG | 32 | Shares PRG with C8 |
| D5 | FLD_D5.PRG | 1 | |

### Field MCB/CGB file lists (example: area A3)

```
FLDCMN.MCB / FLDCMN.CGB   — shared common field assets (always loaded first)
FLD_A3.MCB / FLD_A3.CGB   — main area geometry
FLD_A3_0.MCB / FLD_A3_0.CGB  through  FLD_A3_3.MCB / FLD_A3_3.CGB
{ NULL, NULL }              — terminator
```
Pattern: `FLDCMN` + area base file + numbered subfields.

### Other field-related file types

- **FNT files** (12 on disc): Per-character metrics tables for in-area UI. Format: small header
  (2-byte magic, 2-byte count) followed by per-character width/height/advance data. FLD_T0.FNT
  is used by FLD_C8 (Tower interior areas C8 and D4).
- **EPK files** (E006.EPK, E011.EPK, etc.): **Interactive cutscene streaming containers** — NOT
  SEQ/TON audio bundles. Each contains up to 16 synchronized entity streams (3D models, camera,
  audio). Format not yet decoded. These are the in-engine cinematic sequences in town areas.
