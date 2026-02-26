#!/usr/bin/env python3
"""PNB Palette Extractor for Panzer Dragoon Saga.

Extracts VDP2 Color RAM palette data from .PNB files and exports as
raw binary + JSON metadata + PNG palette swatch visualisations.

PNB files contain u16 big-endian values that are DMA'd to the Saturn's
VDP2 CRAM (Color RAM) at 0x25F00000. The CRAM holds up to 2048 RGB555
color entries across 4KB.

Saturn RGB555 format (per u16 word, big-endian on disc):
  Bit 15:    MSB (set = opaque/valid for LUT, 0 = transparent)
  Bits 14-10: Blue (5 bits)
  Bits 9-5:   Green (5 bits)
  Bits 4-0:   Red (5 bits)

Size distribution on Disc 1 (162 files):
  2048 bytes (1024 colors): 89 files
  4096 bytes (2048 colors): 58 files
  6144 bytes (3072 colors):  6 files
  10240 bytes (5120 colors): 4 files
  14336 bytes (7168 colors): 1 file
  16384 bytes (8192 colors): 2 files
  40960 bytes (20480 colors): 2 files

158 of 162 PNB files have a matching .SCB file (VDP2 tilemap data).
Only 7-8 share a basename with MCB/CGB 3D model files.

Usage:
  python tools/pnb_extract.py --iso disc.bin --list
  python tools/pnb_extract.py --iso disc.bin --extract-all -o output/pnb/
  python tools/pnb_extract.py --iso disc.bin --name DRAGON0.PNB -o output/pnb/
  python tools/pnb_extract.py --input raw/DRAGON0.PNB -o output/pnb/
"""

import struct
import argparse
import json
import os
import sys

# ---------------------------------------------------------------------------
# PNG writer (pure stdlib, no Pillow dependency)
# ---------------------------------------------------------------------------

def _write_png(path, width, height, rgba_rows):
    """Write an RGBA PNG file using only stdlib (struct + zlib)."""
    import zlib

    def _chunk(chunk_type, data):
        c = chunk_type + data
        crc = struct.pack('>I', zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack('>I', len(data)) + c + crc

    ihdr = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    raw = b''
    for row in rgba_rows:
        raw += b'\x00' + row  # filter byte 0 (None) per row
    compressed = zlib.compress(raw)

    sig = b'\x89PNG\r\n\x1a\n'
    with open(path, 'wb') as f:
        f.write(sig)
        f.write(_chunk(b'IHDR', ihdr))
        f.write(_chunk(b'IDAT', compressed))
        f.write(_chunk(b'IEND', b''))


# ---------------------------------------------------------------------------
# Saturn RGB555 decoding
# ---------------------------------------------------------------------------

def rgb555_to_rgba(val):
    """Convert a Saturn RGB555 u16 to (R, G, B, A) tuple (0-255 each).

    Saturn format: MSB | BBBBB | GGGGG | RRRRR
    """
    r = (val & 0x1F) << 3
    g = ((val >> 5) & 0x1F) << 3
    b = ((val >> 10) & 0x1F) << 3
    # Bit 15 = MSB.  For palette entries, 0x0000 is typically transparent.
    # We mark fully-zero entries as transparent; everything else as opaque.
    a = 0 if val == 0 else 255
    return (r, g, b, a)


# ---------------------------------------------------------------------------
# PNB parsing
# ---------------------------------------------------------------------------

def parse_pnb(data):
    """Parse a PNB file and return a list of u16 values (raw CRAM entries).

    Each entry is a big-endian u16 from the file.
    """
    if len(data) < 2:
        raise ValueError(f"PNB file too small: {len(data)} bytes")
    if len(data) % 2 != 0:
        raise ValueError(f"PNB file size not u16-aligned: {len(data)} bytes")

    count = len(data) // 2
    entries = list(struct.unpack('>%dH' % count, data))
    return entries


def decode_palette_colors(entries):
    """Decode raw u16 entries as Saturn RGB555 colors.

    Returns a list of (R, G, B, A) tuples.
    """
    return [rgb555_to_rgba(v) for v in entries]


def analyse_entries(entries):
    """Produce analysis metadata about the raw u16 entries."""
    if not entries:
        return {}

    unique = set(entries)
    msb_set = sum(1 for v in entries if v & 0x8000)
    zero_count = sum(1 for v in entries if v == 0)
    in_cram_range = sum(1 for v in entries if v < 0x1000)

    return {
        'entry_count': len(entries),
        'unique_values': len(unique),
        'min_value': min(entries),
        'max_value': max(entries),
        'msb_set_count': msb_set,
        'zero_count': zero_count,
        'in_cram_range': in_cram_range,
    }


# ---------------------------------------------------------------------------
# PNG palette swatch rendering
# ---------------------------------------------------------------------------

SWATCH_CELL = 8   # pixels per color cell
SWATCH_COLS = 32  # colors per row in the swatch image

def render_palette_swatch(colors, cell_size=SWATCH_CELL, cols=SWATCH_COLS):
    """Render a list of (R, G, B, A) colors as a grid swatch PNG.

    Returns (width, height, list_of_row_bytes) suitable for _write_png.
    """
    num_colors = len(colors)
    rows_of_cells = (num_colors + cols - 1) // cols

    width = cols * cell_size
    height = rows_of_cells * cell_size

    rgba_rows = []
    for cell_row in range(rows_of_cells):
        for pixel_y in range(cell_size):
            row_bytes = bytearray()
            for cell_col in range(cols):
                idx = cell_row * cols + cell_col
                if idx < num_colors:
                    r, g, b, a = colors[idx]
                else:
                    r, g, b, a = 0, 0, 0, 0
                row_bytes.extend(bytes([r, g, b, a]) * cell_size)
            rgba_rows.append(bytes(row_bytes))

    return width, height, rgba_rows


# ---------------------------------------------------------------------------
# Extraction and output
# ---------------------------------------------------------------------------

def extract_and_save(name, data, output_dir):
    """Parse a PNB file and save all outputs.

    Returns (entry_count, analysis_dict).
    """
    entries = parse_pnb(data)
    analysis = analyse_entries(entries)
    colors = decode_palette_colors(entries)
    basename = os.path.splitext(name)[0]

    # 1. Raw binary (byte-for-byte copy)
    raw_path = os.path.join(output_dir, f"{basename}.bin")
    with open(raw_path, 'wb') as f:
        f.write(data)

    # 2. Palette swatch PNG
    if colors:
        # Choose swatch columns based on palette structure
        # 16 colors per bank for 4bpp mode, 256 for 8bpp
        swatch_cols = 16 if len(colors) <= 256 else 32
        w, h, rows = render_palette_swatch(colors, cols=swatch_cols)
        png_path = os.path.join(output_dir, f"{basename}_palette.png")
        _write_png(png_path, w, h, rows)

    # 3. JSON metadata
    # Provide first 64 raw values for inspection
    sample_raw = ['0x%04X' % v for v in entries[:64]]
    sample_rgb = [
        {'hex': '0x%04X' % entries[i], 'r': c[0], 'g': c[1], 'b': c[2]}
        for i, c in enumerate(colors[:64])
    ]

    meta = {
        'source_file': name,
        'file_size_bytes': len(data),
        'format': 'VDP2 CRAM palette data (u16 big-endian)',
        'analysis': {
            **analysis,
            'min_value_hex': '0x%04X' % analysis.get('min_value', 0),
            'max_value_hex': '0x%04X' % analysis.get('max_value', 0),
        },
        'saturn_rgb555_decode': {
            'description': (
                'Each u16 decoded as Saturn RGB555: '
                'MSB(15) | B(14-10) | G(9-5) | R(4-0). '
                'Values expanded from 5-bit to 8-bit by shifting left 3.'
            ),
            'sample_colors': sample_rgb,
        },
        'raw_sample': sample_raw,
        'outputs': {
            'raw_binary': f"{basename}.bin",
            'palette_png': f"{basename}_palette.png",
        },
    }
    meta_path = os.path.join(output_dir, f"{basename}.json")
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)

    return len(entries), analysis


# ---------------------------------------------------------------------------
# Disc helpers
# ---------------------------------------------------------------------------

def find_pnb_files(iso_reader):
    """Find all .PNB files on disc."""
    files = iso_reader.list_files()
    return [f for f in files if f['name'].upper().endswith('.PNB')]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Extract VDP2 palette data from PDS .PNB files.'
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--iso', help='Path to disc image (.bin)')
    source.add_argument('--input', help='Path to a raw PNB file')

    parser.add_argument('--name', help='PNB filename on disc (e.g. DRAGON0.PNB)')
    parser.add_argument('--extract-all', action='store_true',
                        help='Extract all PNB files from disc')
    parser.add_argument('--list', action='store_true',
                        help='List PNB files on disc without extracting')
    parser.add_argument('--output', '-o', default='output/pnb/',
                        help='Output directory (default: output/pnb/)')

    args = parser.parse_args()

    # --- Raw file mode ---
    if args.input:
        os.makedirs(args.output, exist_ok=True)
        with open(args.input, 'rb') as f:
            data = f.read()
        name = os.path.basename(args.input)
        count, analysis = extract_and_save(name, data, args.output)
        print(f"  {name}: {count} entries ({len(data)} bytes)")
        print(f"    MSB-set: {analysis['msb_set_count']}/{count}, "
              f"zeros: {analysis['zero_count']}, "
              f"unique: {analysis['unique_values']}")
        print(f"Done. Output in {args.output}")
        return

    # --- Disc mode ---
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'common'))
    from iso9660 import ISO9660Reader

    iso = ISO9660Reader(args.iso)
    pnb_files = find_pnb_files(iso)

    if not pnb_files:
        print("No .PNB files found on disc.")
        iso.close()
        return

    # List mode
    if args.list:
        print(f"Found {len(pnb_files)} PNB file(s) on disc:\n")
        # Group by size
        from collections import Counter
        size_counts = Counter(f['size'] for f in pnb_files)
        for f in sorted(pnb_files, key=lambda x: x['name']):
            colors = f['size'] // 2
            print(f"  {f['name']:30s}  {f['size']:>6d} bytes  ({colors:>5d} entries)  LBA {f['lba']}")
        print(f"\nSize distribution:")
        for size, count in sorted(size_counts.items()):
            print(f"  {size:>6d} bytes ({size//2:>5d} entries): {count:>3d} files")
        iso.close()
        return

    # Extraction mode
    if args.name:
        target = args.name.upper()
        if not target.endswith('.PNB'):
            target += '.PNB'
        matches = [f for f in pnb_files if f['name'].upper() == target
                   or f['name'].upper().endswith(target)]
        if not matches:
            print(f"PNB file '{args.name}' not found on disc.")
            print("Available PNB files:")
            for f in pnb_files[:10]:
                print(f"  {f['name']}")
            if len(pnb_files) > 10:
                print(f"  ... and {len(pnb_files) - 10} more")
            iso.close()
            return
        pnb_files = matches

    elif not args.extract_all:
        print("Specify --extract-all to extract all PNB files, or --name to extract one.")
        print(f"Found {len(pnb_files)} PNB file(s). Use --list to list them.")
        iso.close()
        return

    os.makedirs(args.output, exist_ok=True)
    print(f"Extracting {len(pnb_files)} PNB file(s)...\n")

    total_entries = 0
    errors = 0
    for finfo in sorted(pnb_files, key=lambda x: x['name']):
        data = iso.extract_file(finfo['lba'], finfo['size'])
        name = os.path.basename(finfo['name'])
        try:
            count, analysis = extract_and_save(name, data, args.output)
            msb = analysis['msb_set_count']
            print(f"  {name:30s}  {count:>5d} entries  "
                  f"MSB={msb:>5d}  unique={analysis['unique_values']:>5d}")
            total_entries += count
        except ValueError as e:
            print(f"  {name:30s}  ERROR: {e}")
            errors += 1

    iso.close()
    print(f"\nDone. {len(pnb_files) - errors} files extracted, "
          f"{total_entries} total entries. Output in {args.output}")
    if errors:
        print(f"  {errors} error(s) encountered.")


if __name__ == '__main__':
    main()
