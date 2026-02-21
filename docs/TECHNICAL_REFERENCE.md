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
- **Out-of-bounds tone_off values** occur in files that are part of SND bundles (e.g. BOS5BGM.BIN). These reference PCM data loaded from a companion bank into SCSP RAM. Skip gracefully.
- **8-bit signed PCM** must be converted to unsigned for WAV: `wav_byte = pcm_byte + 128`.
- **16-bit PCM** is big-endian signed; must be byte-swapped to little-endian for WAV.

### SND Bundle Layout

The EPISODE and INTER SND files are concatenated archives with no header. Known layouts for PDS USA Disc 1 are documented in `docs/antigravity-tasks/TASK_SEQ_EXTRACTOR.md`. These must be split at the documented byte offsets before TON banks inside them can be processed.

### Tool

`tools/ton_to_wav.py` — extracts all unique PCM samples from a standalone BIN tone bank to individual WAV files.

```bash
python tools/ton_to_wav.py --input output/seq_extract/raw/KOGATA.BIN --output output/ton_wav_test/KOGATA/
```
