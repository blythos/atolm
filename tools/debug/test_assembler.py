import struct
import zlib
import os

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
rgba_palette[0] = (128, 128, 128, 255)  # gray background to see transparent

with open(r"e:\Dev\atolm\output\WARNING.SCB", "rb") as f:
    scb_data = f.read()

def get_pixel(tile_data, x, y):
    cell_x = x // 8
    cell_y = y // 8
    cell_idx = cell_y * 2 + cell_x
    in_cell_x = x % 8
    in_cell_y = y % 8
    cell_offset = cell_idx * 32
    row_offset = cell_offset + in_cell_y * 4
    byte_offset = row_offset + in_cell_x // 2
    if byte_offset >= len(tile_data): return 0
    b = tile_data[byte_offset]
    if in_cell_x % 2 == 0:
        return (b >> 4) & 0xF
    else:
        return b & 0xF

TILE_SIZE_BYTES = 128
num_tiles = len(scb_data) // TILE_SIZE_BYTES
width_tiles = 16
height_tiles = (num_tiles + width_tiles - 1) // width_tiles

img_width = width_tiles * 16
img_height = height_tiles * 16
rgba_rows = [bytearray() for _ in range(img_height)]

for ty in range(height_tiles):
    for tx in range(width_tiles):
        tile_idx = ty * width_tiles + tx
        if tile_idx < num_tiles:
            tile_data = scb_data[tile_idx * 128: (tile_idx+1)*128]
            for py in range(16):
                for px in range(16):
                    px_val = get_pixel(tile_data, px, py)
                    r, g, b, a = rgba_palette[px_val]
                    rgba_rows[ty * 16 + py].extend([r, g, b, a])
        else:
            for py in range(16):
                rgba_rows[ty * 16 + py].extend([0, 0, 0, 0] * 16)

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
        
_write_png(r"e:\Dev\atolm\output\warning_raw_scb.png", img_width, img_height, [bytes(r) for r in rgba_rows])
print("Saved warning_raw_scb.png")
