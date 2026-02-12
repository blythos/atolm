# Quick Reference Card

## Reading Values from PDS Binary Data (Big-Endian)

```python
import struct
def read_u32(d, o): return struct.unpack('>I', d[o:o+4])[0]
def read_s32(d, o): return struct.unpack('>i', d[o:o+4])[0]
def read_u16(d, o): return struct.unpack('>H', d[o:o+2])[0]
def read_s16(d, o): return struct.unpack('>h', d[o:o+2])[0]
```

## Fixed-Point Conversions

```python
vertex_float = raw_s16 * 16 / 4096.0     # 12.4 vertex → output coords
bone_trans_float = raw_s32 / 4096.0       # 16.16 translation → output coords  
bone_rot_radians = raw_s32 / 65536.0 * 2 * math.pi  # Saturn angle → radians
bone_scale_float = raw_s32 / 65536.0      # 16.16 scale → float (rest = 1.0)
```

## Texture Address from MCB Quad Fields

```python
texture_byte_offset = CMDSRCA * 8    # offset into CGB file
palette_byte_offset = CMDCOLR * 8    # offset into CGB file (LUT mode)
tex_width = (CMDSIZE & 0x3F00) >> 5  # pixels
tex_height = CMDSIZE & 0xFF          # pixels
color_mode = (CMDPMOD >> 3) & 7      # 0=4bpp bank, 1=4bpp LUT, 5=16bpp
```

## Saturn RGB555 → RGBA8888

```python
R = (color16 & 0x1F) << 3
G = ((color16 >> 5) & 0x1F) << 3
B = ((color16 >> 10) & 0x1F) << 3
A = 255 if (color16 & 0x8000) else 0  # bit 15 = valid color for LUT entries
```

## Read a Sector from Raw Disc Image

```python
SECTOR_SIZE = 2352; HEADER = 16; DATA = 2048
f.seek(sector_num * SECTOR_SIZE)
user_data = f.read(SECTOR_SIZE)[HEADER:HEADER + DATA]
```

## Files on Disc — User Has

The user has the Disc 1 raw track image uploaded. When starting a new conversation that needs disc access, extract it from the user's uploaded file using the ISO9660 reader code. The disc image filename pattern is: `Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin`
