#!/usr/bin/env python3
"""FNT Font Extractor for Panzer Dragoon Saga.

Extracts VDP2 bitmap font glyphs from .FNT files and exports them as
PNG sprite sheets + JSON metadata.

FNT format (all u16 big-endian):
  Offset 0x00: u16  glyph_count
  Offset 0x02: u16  font_type (4 = normal, 5 = extended/sprites)
  Offset 0x04-0x0F: u16[6] reserved (header padding)
  Offset 0x10: u16[16 * glyph_count] glyph bitmaps (1bpp, 16x16 each)

Each glyph = 16 rows of u16, MSB = leftmost pixel.
Derived from yaz0r's Azel decompilation (loadFnt, resetVdp2StringsSub1,
loadCharacterToVdp2 in VDP2.cpp).

Usage:
  python tools/fnt_extract.py --iso disc.bin --all --output output/fonts/
  python tools/fnt_extract.py --iso disc.bin --name MENU.FNT --output output/fonts/
  python tools/fnt_extract.py --input raw/MENU.FNT --output output/fonts/
"""

import struct
import argparse
import json
import os
import sys

# -- PNG writer (pure stdlib, no Pillow dependency) --

def _write_png(path, width, height, rgba_rows):
    """Write an RGBA PNG file using only stdlib (struct + zlib)."""
    import zlib

    def _chunk(chunk_type, data):
        c = chunk_type + data
        crc = struct.pack('>I', zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack('>I', len(data)) + c + crc

    # IHDR
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    # IDAT
    raw = b''
    for row in rgba_rows:
        raw += b'\x00' + row  # filter byte 0 (None) per row
    compressed = zlib.compress(raw)
    # Assemble
    sig = b'\x89PNG\r\n\x1a\n'
    with open(path, 'wb') as f:
        f.write(sig)
        f.write(_chunk(b'IHDR', ihdr))
        f.write(_chunk(b'IDAT', compressed))
        f.write(_chunk(b'IEND', b''))


# -- FNT parsing --

HEADER_SIZE = 16  # 8 u16 values
GLYPH_ROWS = 16
GLYPH_COLS = 16
GLYPH_U16S = 16   # 16 u16 values per glyph

def parse_fnt(data):
    """Parse an FNT file and return (glyph_count, font_type, list_of_glyphs).
    
    Each glyph is a list of 16 ints (u16), representing 16 rows of 1bpp pixels.
    """
    if len(data) < HEADER_SIZE:
        raise ValueError(f"FNT file too small: {len(data)} bytes (need at least {HEADER_SIZE})")

    glyph_count = struct.unpack('>H', data[0:2])[0]
    font_type = struct.unpack('>H', data[2:4])[0]

    expected_size = HEADER_SIZE + glyph_count * GLYPH_U16S * 2
    if len(data) < expected_size:
        raise ValueError(
            f"FNT file truncated: {len(data)} bytes, expected {expected_size} "
            f"for {glyph_count} glyphs"
        )

    glyphs = []
    offset = HEADER_SIZE
    for i in range(glyph_count):
        rows = []
        for r in range(GLYPH_U16S):
            val = struct.unpack('>H', data[offset:offset+2])[0]
            rows.append(val)
            offset += 2
        glyphs.append(rows)

    return glyph_count, font_type, glyphs


def render_sprite_sheet(glyphs, cols=16):
    """Render glyphs into an RGBA sprite sheet.
    
    Returns (width, height, list_of_row_bytes) suitable for _write_png.
    """
    num_glyphs = len(glyphs)
    rows_of_glyphs = (num_glyphs + cols - 1) // cols

    width = cols * GLYPH_COLS
    height = rows_of_glyphs * GLYPH_ROWS

    # Build image as rows of RGBA bytes
    rgba_rows = []
    for glyph_row in range(rows_of_glyphs):
        for pixel_row in range(GLYPH_ROWS):
            row_bytes = bytearray()
            for glyph_col in range(cols):
                glyph_idx = glyph_row * cols + glyph_col
                if glyph_idx < num_glyphs:
                    bitmap_u16 = glyphs[glyph_idx][pixel_row]
                    for bit in range(GLYPH_COLS):
                        if bitmap_u16 & (0x8000 >> bit):
                            row_bytes.extend(b'\xFF\xFF\xFF\xFF')  # white, opaque
                        else:
                            row_bytes.extend(b'\x00\x00\x00\x00')  # transparent
                else:
                    # Empty cell
                    row_bytes.extend(b'\x00\x00\x00\x00' * GLYPH_COLS)
            rgba_rows.append(bytes(row_bytes))

    return width, height, rgba_rows


def render_single_glyph(glyph):
    """Render a single 16x16 glyph into RGBA rows."""
    rgba_rows = []
    for pixel_row in range(GLYPH_ROWS):
        row_bytes = bytearray()
        bitmap_u16 = glyph[pixel_row]
        for bit in range(GLYPH_COLS):
            if bitmap_u16 & (0x8000 >> bit):
                row_bytes.extend(b'\xFF\xFF\xFF\xFF')
            else:
                row_bytes.extend(b'\x00\x00\x00\x00')
        rgba_rows.append(bytes(row_bytes))
    return GLYPH_COLS, GLYPH_ROWS, rgba_rows


# -- Disc extraction helpers --

def find_fnt_files(iso_reader):
    """Find all .FNT files on disc."""
    files = iso_reader.list_files()
    return [f for f in files if f['name'].upper().endswith('.FNT')]


def extract_and_save(name, data, output_dir, individual=False):
    """Parse an FNT file and save outputs."""
    glyph_count, font_type, glyphs = parse_fnt(data)
    basename = os.path.splitext(name)[0]

    # Sprite sheet
    sheet_cols = 16
    w, h, rows = render_sprite_sheet(glyphs, cols=sheet_cols)
    sheet_path = os.path.join(output_dir, f"{basename}_font.png")
    _write_png(sheet_path, w, h, rows)

    # Individual glyphs
    if individual:
        glyph_dir = os.path.join(output_dir, basename)
        os.makedirs(glyph_dir, exist_ok=True)
        for i, glyph in enumerate(glyphs):
            gw, gh, grows = render_single_glyph(glyph)
            glyph_path = os.path.join(glyph_dir, f"glyph_{i:03d}.png")
            _write_png(glyph_path, gw, gh, grows)

    # JSON metadata
    meta = {
        'source_file': name,
        'glyph_count': glyph_count,
        'font_type': font_type,
        'font_type_desc': 'extended/sprites' if font_type == 5 else 'normal',
        'glyph_size': [GLYPH_COLS, GLYPH_ROWS],
        'sheet_grid': [sheet_cols, (glyph_count + sheet_cols - 1) // sheet_cols],
        'sheet_file': f"{basename}_font.png",
        'file_size_bytes': len(data),
        'char_mapping_note': (
            'Glyphs typically map to ASCII starting from 0x20 (space). '
            'Glyph index N corresponds to character code 0x20 + N.'
        ),
    }
    meta_path = os.path.join(output_dir, f"{basename}_font.json")
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)

    return glyph_count, font_type


def main():
    parser = argparse.ArgumentParser(
        description='Extract bitmap font glyphs from PDS .FNT files.'
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--iso', help='Path to disc image (.bin)')
    source.add_argument('--input', help='Path to a raw FNT file')

    parser.add_argument('--name', help='FNT filename on disc (e.g. MENU.FNT)')
    parser.add_argument('--all', action='store_true', help='Extract all FNT files from disc')
    parser.add_argument('--individual', action='store_true',
                        help='Also export individual glyph PNGs')
    parser.add_argument('--output', '-o', default='output/fonts/',
                        help='Output directory (default: output/fonts/)')
    parser.add_argument('--scan', action='store_true',
                        help='List FNT files on disc without extracting')

    args = parser.parse_args()
    os.makedirs(args.output, exist_ok=True)

    if args.input:
        # Raw file mode
        with open(args.input, 'rb') as f:
            data = f.read()
        name = os.path.basename(args.input)
        gc, ft = extract_and_save(name, data, args.output, args.individual)
        print(f"  {name}: {gc} glyphs, type {ft}")
        print(f"Done. Output in {args.output}")
        return

    # Disc mode
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'common'))
    from iso9660 import ISO9660Reader

    iso = ISO9660Reader(args.iso)
    fnt_files = find_fnt_files(iso)

    if not fnt_files:
        print("No .FNT files found on disc.")
        iso.close()
        return

    if args.scan:
        print(f"Found {len(fnt_files)} FNT file(s) on disc:\n")
        for f in sorted(fnt_files, key=lambda x: x['name']):
            print(f"  {f['name']:30s}  {f['size']:>6d} bytes  LBA {f['lba']}")
        iso.close()
        return

    if args.name:
        # Single file extraction
        target = args.name.upper()
        matches = [f for f in fnt_files if f['name'].upper().endswith(target)]
        if not matches:
            print(f"FNT file '{args.name}' not found on disc.")
            print("Available FNT files:")
            for f in fnt_files:
                print(f"  {f['name']}")
            iso.close()
            return
        fnt_files = matches

    if not args.all and not args.name:
        print("Specify --all to extract all FNT files, or --name to extract one.")
        print(f"Found {len(fnt_files)} FNT file(s). Use --scan to list them.")
        iso.close()
        return

    print(f"Extracting {len(fnt_files)} FNT file(s)...\n")

    for finfo in sorted(fnt_files, key=lambda x: x['name']):
        data = iso.extract_file(finfo['lba'], finfo['size'])
        name = os.path.basename(finfo['name'])
        try:
            gc, ft = extract_and_save(name, data, args.output, args.individual)
            print(f"  {name:25s}  {gc:4d} glyphs  type {ft}")
        except ValueError as e:
            print(f"  {name:25s}  ERROR: {e}")

    iso.close()
    print(f"\nDone. Output in {args.output}")


if __name__ == '__main__':
    main()
