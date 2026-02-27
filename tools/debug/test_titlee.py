import struct
import zlib

with open(r"e:\Dev\atolm\output\TITLEE.SCB", "rb") as f:
    scb_data = f.read()

with open(r"e:\Dev\atolm\output\TITLEE.PNB", "rb") as f:
    pnb_data = f.read()

# Generate a grayscale palette for 256 colors since we don't have the exact TITLEE palette here
rgba_palette = []
for i in range(256):
    rgba_palette.append((i, i, i, 255))
rgba_palette[0] = (255, 0, 255, 255) # transparent mapped to magenta

def get_pixel_8bpp(tile_data, x, y):
    if not tile_data: return 0
    cell_idx = (y // 8) * 2 + (x // 8)
    # 8bpp means 1 pixel = 1 byte. 1 cell = 64 bytes.
    # 1 row in a cell = 8 bytes.
    byte_offset = cell_idx * 64 + (y % 8) * 8 + (x % 8)
    if byte_offset >= len(tile_data): return 0
    return tile_data[byte_offset]

entries = struct.unpack(f">{len(pnb_data)//2}H", pnb_data)
width_tiles = 64
height_tiles = len(entries) // width_tiles

img_width = width_tiles * 16
img_height = height_tiles * 16

rgba_rows = [bytearray() for _ in range(img_height)]

for ty in range(height_tiles):
    for tx in range(width_tiles):
        val = entries[ty * width_tiles + tx]
        # In Mode 1 (CNSM=1), charset is 12 bits. 0-4095
        char_idx = val & 0xFFF
        
        # TITLEE base is 0
        tile_offset = char_idx * 256  # 16x16 8bpp = 256 bytes per tile
        
        if tile_offset + 256 <= len(scb_data):
            tile_data = scb_data[tile_offset:tile_offset+256]
        else:
            tile_data = None
            
        for py in range(16):
            target_y = ty * 16 + py
            for px in range(16):
                px_val = get_pixel_8bpp(tile_data, px, py)
                r, g, b, a = rgba_palette[px_val]
                rgba_rows[target_y].extend([r, g, b, a])

def _write_png(path, width, height, rgba_rows):
    def _chunk(chunk_type, data):
        c = chunk_type + data
        crc = struct.pack('>I', zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack('>I', len(data)) + c + crc
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0) # 8-bit truecolor with alpha
    raw = b''
    for row in rgba_rows:
        raw += b'\x00' + row
    compressed = zlib.compress(raw)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n')
        f.write(_chunk(b'IHDR', ihdr))
        f.write(_chunk(b'IDAT', compressed))
        f.write(_chunk(b'IEND', b''))
        
_write_png(r"e:\Dev\atolm\output\titlee_final.png", img_width, img_height, [bytes(r) for r in rgba_rows])
print("Saved titlee_final.png")
