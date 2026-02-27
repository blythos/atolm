import struct
import zlib

with open(r"e:\Dev\atolm\output\WARNING.SCB", "rb") as f:
    scb_data = f.read()

with open(r"e:\Dev\atolm\output\WARNING.PNB", "rb") as f:
    pnb_data = f.read()

PALETTE = [
    0x0000, 0x0842, 0x1084, 0x18C6, 0x2108, 0x294A, 0x318C, 0x39CE,
    0x4210, 0x4631, 0x5294, 0x5EF7, 0x6739, 0x6F7B, 0x77BD, 0x7FFF
]

rgba_palette = []
for color in PALETTE:
    r = (color & 0x1F) << 3
    g = ((color >> 5) & 0x1F) << 3
    b = ((color >> 10) & 0x1F) << 3
    rgba_palette.append((r, g, b, 255))
rgba_palette[0] = (64, 64, 64, 255)  # gray background to show everything

def get_pixel(tile_data, x, y):
    if not tile_data: return 0
    cell_idx = (y // 8) * 2 + (x // 8)
    byte_offset = cell_idx * 32 + (y % 8) * 4 + ((x % 8) // 2)
    b = tile_data[byte_offset]
    return (b >> 4) & 0xF if x % 2 == 0 else b & 0xF

entries = struct.unpack(f">{len(pnb_data)//2}H", pnb_data)
width_tiles = 64
height_tiles = len(entries) // width_tiles

img_width = width_tiles * 16
img_height = height_tiles * 16

rgba_rows = [bytearray() for _ in range(img_height)]

for ty in range(height_tiles):
    for tx in range(width_tiles):
        val = entries[ty * width_tiles + tx]
        char_idx = val & 0xFFF
        
        if char_idx >= 512:
            tile_offset = (char_idx - 512) * 128
            if tile_offset + 128 <= len(scb_data):
                tile_data = scb_data[tile_offset:tile_offset+128]
            else:
                tile_data = None
        else:
            tile_data = None
            
        for py in range(16):
            target_y = ty * 16 + py
            for px in range(16):
                px_val = get_pixel(tile_data, px, py)
                r, g, b, a = rgba_palette[px_val]
                rgba_rows[target_y].extend([r, g, b, a])

def _write_png(path, width, height, rgba_rows):
    def _chunk(chunk_type, data):
        c = chunk_type + data
        crc = struct.pack('>I', zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack('>I', len(data)) + c + crc
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    raw = b''
    for row in rgba_rows:
        raw += b'\x00' + row
    compressed = zlib.compress(raw)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n')
        f.write(_chunk(b'IHDR', ihdr))
        f.write(_chunk(b'IDAT', compressed))
        f.write(_chunk(b'IEND', b''))
        
_write_png(r"e:\Dev\atolm\output\warning_final.png", img_width, img_height, [bytes(r) for r in rgba_rows])
print("Saved warning_final.png")
