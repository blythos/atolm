#!/usr/bin/env python3
"""PNB Extractor for Panzer Dragoon Saga.

Extracts VDP2 Pattern Name Data from .PNB files and exports as
raw binary + JSON metadata + PNG tile map assemblies.

PNB = Pattern Name Block. Each PNB file contains a flat array of u16
big-endian VDP2 pattern name entries — i.e. a tile map. The
matching .SCB file (Screen Cell Bitmap) holds the tile graphics data;
the PNB tells the VDP2 *which* tile to draw at each map position and
with what palette / flip attributes.

VDP2 addressing (from Azel reverse-engineering):
  - Character address in VRAM = character_number × 0x20 (always)
  - For 2×2 cell mode (16×16 tiles), the effective multiplier is
    character_number × 0x80 because each tile occupies 4 cells.
  - PNB planes are 32×32 tiles (1024 entries each) for 2×2 cell mode.
  - BPP is detected from character number stepping:
      Step of 1 between adjacent tiles → 4bpp (128 bytes/tile)
      Step of 2 between adjacent tiles → 8bpp (256 bytes/tile)

Known VDP2 configurations from Azel source (o_title.cpp, titleScreen.cpp):
  WARNING.SCB: CHCN=0(4bpp), CHSZ=1(2×2), CNSM=1(12-bit), SCB@0x10000
  TITLEE.SCB:  CHCN=1(8bpp), CHSZ=1(2×2), CNSM=1(12-bit), SCB@0x20000

Usage:
  python tools/pnb_extract.py --input raw/TITLEE.PNB -o output/pnb/
  python tools/pnb_extract.py --input raw/TITLEE.PNB --scb raw/TITLEE.SCB -o output/pnb/
  python tools/pnb_extract.py --iso disc.bin --extract-all -o output/pnb/
  python tools/pnb_extract.py --iso disc.bin --name ZOAH.PNB -o output/pnb/
  python tools/pnb_extract.py --iso disc.bin --list
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
    raw = b''.join(b'\x00' + row for row in rgba_rows)
    compressed = zlib.compress(raw)

    sig = b'\x89PNG\r\n\x1a\n'
    with open(path, 'wb') as f:
        f.write(sig)
        f.write(_chunk(b'IHDR', ihdr))
        f.write(_chunk(b'IDAT', compressed))
        f.write(_chunk(b'IEND', b''))


# ---------------------------------------------------------------------------
# VDP2 Pattern Name decoding
# ---------------------------------------------------------------------------

def decode_pattern_name_10bit(val):
    """Decode a u16 VDP2 1-word pattern name entry (10-bit character number).

    Returns dict with palette_number, h_flip, v_flip, character_number.
    """
    return {
        'palette_number': (val >> 12) & 0x7,
        'h_flip': bool((val >> 11) & 1),
        'v_flip': bool((val >> 10) & 1),
        'character_number': val & 0x3FF,
    }


def decode_pattern_name_12bit(val):
    """Decode a u16 VDP2 1-word pattern name entry (12-bit character number).

    In CNSM=1 mode, bits 11-0 are all character number (no flip/palette).
    """
    return {
        'palette_number': 0,
        'h_flip': False,
        'v_flip': False,
        'character_number': val & 0xFFF,
    }


# ---------------------------------------------------------------------------
# PNB parsing
# ---------------------------------------------------------------------------

def parse_pnb(data):
    """Parse a PNB file and return a list of u16 values (raw pattern name entries)."""
    if len(data) < 2:
        raise ValueError(f"PNB file too small: {len(data)} bytes")
    if len(data) % 2 != 0:
        raise ValueError(f"PNB file size not u16-aligned: {len(data)} bytes")

    count = len(data) // 2
    entries = list(struct.unpack('>%dH' % count, data))
    return entries


def detect_addressing(entries):
    """Detect BPP and character base from pattern name entries.

    Returns (bpp, base_char, is_12bit).

    Detection logic:
    - If any character number exceeds 1023, we must be in 12-bit mode
    - Character step of 2 between adjacent tiles → 8bpp
    - Character step of 1 → 4bpp
    """
    char_12 = [e & 0xFFF for e in entries]
    max_char = max(char_12) if char_12 else 0
    min_char = min(char_12) if char_12 else 0

    is_12bit = max_char > 1023

    # Detect step: look at consecutive non-zero entries
    steps = []
    for i in range(len(char_12) - 1):
        a, b = char_12[i], char_12[i+1]
        if a > 0 and b > 0 and a != b:
            diff = abs(b - a)
            if diff in (1, 2):
                steps.append(diff)
            if len(steps) >= 20:
                break

    if steps:
        avg_step = sum(steps) / len(steps)
        bpp = 8 if avg_step > 1.5 else 4
    else:
        # Fallback: guess from SCB size ratio if available
        bpp = 4

    return bpp, min_char, is_12bit


def analyse_entries(entries):
    """Produce analysis metadata about the pattern name entries."""
    if not entries:
        return {}

    chars_12 = [e & 0xFFF for e in entries]
    chars_10 = [e & 0x3FF for e in entries]
    max_12 = max(chars_12)
    is_12bit = max_12 > 1023

    if is_12bit:
        decoded = [decode_pattern_name_12bit(v) for v in entries]
    else:
        decoded = [decode_pattern_name_10bit(v) for v in entries]

    palette_counts = {}
    flip_count = 0
    char_nums = set()
    for d in decoded:
        p = d['palette_number']
        palette_counts[p] = palette_counts.get(p, 0) + 1
        if d['h_flip'] or d['v_flip']:
            flip_count += 1
        char_nums.add(d['character_number'])

    bpp, base_char, _ = detect_addressing(entries)

    return {
        'entry_count': len(entries),
        'unique_raw_values': len(set(entries)),
        'unique_character_numbers': len(char_nums),
        'max_character_number': max(d['character_number'] for d in decoded),
        'min_character_number': min(d['character_number'] for d in decoded),
        'palettes_used': dict(sorted(palette_counts.items())),
        'flipped_entries': flip_count,
        'min_raw': min(entries),
        'max_raw': max(entries),
        'detected_bpp': bpp,
        'detected_12bit': is_12bit,
    }


# ---------------------------------------------------------------------------
# SCB Tilemap Assembly
# ---------------------------------------------------------------------------

def assemble_tilemap(entries, scb_data, bpp=None, palette_data=None):
    """Assemble the tilemap from PNB entries and SCB character data.

    Handles:
    - 2×2 cell mode (16×16 tiles) with 32×32 tile planes
    - Automatic plane stitching (Plane A = left, Plane B = right, etc.)
    - 4bpp and 8bpp character data
    - 12-bit and 10-bit character number modes

    Returns (width, height, list_of_rgba_row_bytes).
    """
    # Detect addressing parameters
    det_bpp, base_char, is_12bit = detect_addressing(entries)
    if bpp is None:
        bpp = det_bpp

    # For 2×2 cells, each plane is 32×32 entries (1024)
    PLANE_SIZE = 1024  # entries per plane
    PLANE_W = 32       # tiles per plane row
    PLANE_H = 32       # tiles per plane column
    TILE_PX = 16       # pixels per tile (2×2 cells)

    num_planes = len(entries) // PLANE_SIZE
    if num_planes < 1:
        num_planes = 1

    # Determine plane layout:
    # 1 plane  → 32×32 tiles
    # 2 planes → 64×32 tiles (side by side)
    # 3+ planes → each rendered separately (stacked vertically)
    if num_planes <= 2:
        planes_h = num_planes  # horizontal plane count
        planes_v = 1
    elif num_planes == 4:
        planes_h = 2
        planes_v = 2
    else:
        # For 3, 5, 6, etc. — stack vertically (separate screens)
        planes_h = 1
        planes_v = num_planes

    map_w = planes_h * PLANE_W  # total tiles wide
    map_h = planes_v * PLANE_H  # total tiles tall
    img_w = map_w * TILE_PX
    img_h = map_h * TILE_PX

    # Build the palette
    rgba_palette = []
    if palette_data:
        # Saturn VDP2 CRAM is 16-bit big-endian RGB555 (with top bit often 0 or priority)
        # R = bits 0-4, G = bits 5-9, B = bits 10-14
        num_colors = len(palette_data) // 2
        
        for i in range(num_colors):
            val = struct.unpack_from('>H', palette_data, i * 2)[0]
            r = (val & 0x1F) << 3
            g = ((val >> 5) & 0x1F) << 3
            b_c = ((val >> 10) & 0x1F) << 3
            # Alpha: VDP2 often uses colour 0 as background. We map fully opaque for accurate pixel reproduction.
            rgba_palette.append((r, g, b_c, 255))
            
        # Pad palette up to minimum required sizes
        target_len = 256 if bpp == 8 else 16
        while len(rgba_palette) < target_len:
            rgba_palette.append((255, 0, 255, 255)) # bright magenta missing
    else:
        # Greyscale fallback
        if bpp == 4:
            for i in range(16):
                v = i * 17  # 0..255
                rgba_palette.append((v, v, v, 255))
        else:
            for i in range(256):
                rgba_palette.append((i, i, i, 255))

    # Tile data sizes
    cell_bytes = 32 if bpp == 4 else 64    # bytes per 8×8 cell
    tile_bytes = cell_bytes * 4             # bytes per 16×16 tile (4 cells)

    # Character multiplier: 2×2 cells → char_num × 0x80 ALWAYS (character indices skip for 8bpp)
    CHAR_MULT = 0x80

    # Calculate VRAM base from minimum character number
    vram_base = base_char * CHAR_MULT

    rgba_rows = [bytearray() for _ in range(img_h)]

    for plane_idx in range(num_planes):
        # Determine this plane's position in output
        px_offset = (plane_idx % planes_h) * PLANE_W
        py_offset = (plane_idx // planes_h) * PLANE_H

        plane_entries = entries[plane_idx * PLANE_SIZE:(plane_idx + 1) * PLANE_SIZE]
        if len(plane_entries) < PLANE_SIZE:
            plane_entries.extend([0] * (PLANE_SIZE - len(plane_entries)))

        for ty in range(PLANE_H):
            for tx in range(PLANE_W):
                val = plane_entries[ty * PLANE_W + tx]

                if is_12bit:
                    d = decode_pattern_name_12bit(val)
                else:
                    d = decode_pattern_name_10bit(val)

                char_num = d['character_number']
                pal_num = d['palette_number']
                h_flip = d['h_flip']
                v_flip = d['v_flip']

                # Calculate SCB offset
                tile_vram_addr = char_num * CHAR_MULT
                scb_offset = tile_vram_addr - vram_base

                if scb_offset >= 0 and scb_offset + tile_bytes <= len(scb_data):
                    tile_data = scb_data[scb_offset:scb_offset + tile_bytes]
                else:
                    tile_data = b'\x00' * tile_bytes

                # Render 16×16 tile (4 cells in 2×2 arrangement)
                out_tx = (px_offset + tx) * TILE_PX
                out_ty = (py_offset + ty) * TILE_PX

                for py in range(TILE_PX):
                    src_y = (TILE_PX - 1 - py) if v_flip else py
                    target_y = out_ty + py

                    for px in range(TILE_PX):
                        src_x = (TILE_PX - 1 - px) if h_flip else px

                        # Cell layout: TL=0, TR=1, BL=2, BR=3
                        cell_idx = (src_y // 8) * 2 + (src_x // 8)
                        local_y = src_y % 8
                        local_x = src_x % 8

                        if bpp == 4:
                            byte_off = cell_idx * 32 + local_y * 4 + local_x // 2
                            b_byte = tile_data[byte_off]
                            px_val = (b_byte >> 4) if local_x % 2 == 0 else (b_byte & 0xF)
                            
                            pal_base = pal_num * 16
                            color_idx = (pal_base + px_val) % len(rgba_palette)
                        else:
                            byte_off = cell_idx * 64 + local_y * 8 + local_x
                            px_val = tile_data[byte_off]
                            
                            # 8bpp usually uses offset 0, but sometimes uses palette banks
                            pal_base = pal_num * 256
                            color_idx = (pal_base + px_val) % len(rgba_palette)

                        r, g, b_c, a = rgba_palette[color_idx]
                        if bpp == 4 and px_val == 0:
                            a = 0 # 4bpp index 0 is always transparent
                            
                        rgba_rows[target_y].extend([r, g, b_c, a])

    return img_w, img_h, rgba_rows


# ---------------------------------------------------------------------------
# Tile map visualisation (fallback when no SCB is available)
# ---------------------------------------------------------------------------

# 8 distinct palette colours for visualisation (one per palette number 0-7)
PALETTE_VIS_COLORS = [
    (180,  30,  30, 255),  # 0: red
    ( 30, 180,  30, 255),  # 1: green
    ( 30,  30, 180, 255),  # 2: blue
    (180, 180,  30, 255),  # 3: yellow
    (180,  30, 180, 255),  # 4: magenta
    ( 30, 180, 180, 255),  # 5: cyan
    (180, 120,  30, 255),  # 6: orange
    (120,  30, 180, 255),  # 7: purple
]


def render_tilemap_vis(entries, map_width=64):
    """Render a colour-coded tile map visualisation (no SCB data)."""
    num_entries = len(entries)
    map_height = (num_entries + map_width - 1) // map_width

    scale = 2
    width = map_width * scale
    height = map_height * scale

    decoded = [decode_pattern_name_10bit(v) for v in entries]

    max_chars_per_pal = {}
    for d in decoded:
        p = d['palette_number']
        c = d['character_number']
        if p not in max_chars_per_pal or c > max_chars_per_pal[p]:
            max_chars_per_pal[p] = c

    rgba_rows = []
    for cell_row in range(map_height):
        row_bytes = bytearray()
        for cell_col in range(map_width):
            idx = cell_row * map_width + cell_col
            if idx < num_entries:
                d = decoded[idx]
                base = PALETTE_VIS_COLORS[d['palette_number']]
                max_c = max(max_chars_per_pal.get(d['palette_number'], 1), 1)
                brightness = 0.3 + 0.7 * (d['character_number'] / max_c)
                r = min(255, int(base[0] * brightness))
                g = min(255, int(base[1] * brightness))
                b = min(255, int(base[2] * brightness))
                pixel = bytes([r, g, b, 255]) * scale
            else:
                pixel = bytes([0, 0, 0, 0]) * scale
            row_bytes.extend(pixel)

        row = bytes(row_bytes)
        for _ in range(scale):
            rgba_rows.append(row)

    return width, height, rgba_rows


# ---------------------------------------------------------------------------
# Extraction and output
# ---------------------------------------------------------------------------

def extract_and_save(name, data, output_dir, scb_data=None, palette_data=None):
    """Parse a PNB file and save all outputs.

    Returns (entry_count, analysis_dict).
    """
    entries = parse_pnb(data)
    analysis = analyse_entries(entries)
    basename = os.path.splitext(name)[0]

    # 1. Raw binary (byte-for-byte copy)
    raw_path = os.path.join(output_dir, f"{basename}.bin")
    with open(raw_path, 'wb') as f:
        f.write(data)

    # 2. Tile map PNG
    png_suffix = '_tilemap_vis.png'
    if entries:
        if scb_data and len(scb_data) >= 128:
            # Assemble real tilemap from SCB
            try:
                w, h, rows = assemble_tilemap(entries, scb_data, palette_data=palette_data)
                png_suffix = '_assembled.png'
            except Exception as e:
                print(f"    SCB assembly failed ({e}), falling back to vis")
                count = len(entries)
                map_w = 32 if count <= 1024 else (64 if count <= 4096 else 128)
                w, h, rows = render_tilemap_vis(entries, map_width=map_w)
        else:
            count = len(entries)
            map_w = 32 if count <= 1024 else (64 if count <= 4096 else 128)
            w, h, rows = render_tilemap_vis(entries, map_width=map_w)

        png_path = os.path.join(output_dir, f"{basename}{png_suffix}")
        _write_png(png_path, w, h, rows)

    # 3. JSON metadata
    sample_decoded = []
    is_12bit = analysis.get('detected_12bit', False)
    decode_fn = decode_pattern_name_12bit if is_12bit else decode_pattern_name_10bit
    for i, v in enumerate(entries[:32]):
        d = decode_fn(v)
        d['raw_hex'] = '0x%04X' % v
        d['index'] = i
        sample_decoded.append(d)

    meta = {
        'source_file': name,
        'file_size_bytes': len(data),
        'format': 'VDP2 Pattern Name Data (u16 big-endian tile map entries)',
        'analysis': {
            **analysis,
            'min_raw_hex': '0x%04X' % analysis.get('min_raw', 0),
            'max_raw_hex': '0x%04X' % analysis.get('max_raw', 0),
            'scb_present': scb_data is not None,
            'scb_size': len(scb_data) if scb_data else 0,
            'palette_present': palette_data is not None,
        },
        'sample_entries': sample_decoded,
        'outputs': {
            'raw_binary': f"{basename}.bin",
            'tilemap_png': f"{basename}{png_suffix}",
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


def find_scb_file(iso_reader, pnb_name, all_files=None):
    """Find the matching .SCB file for a PNB on disc."""
    basename = os.path.splitext(pnb_name)[0]
    scb_name = basename + '.SCB'
    if all_files is None:
        all_files = iso_reader.list_files()
    matches = [f for f in all_files if f['name'].upper() == scb_name.upper()]
    return matches[0] if matches else None


def find_prg_file(iso_reader, pnb_name, all_files=None):
    """Find the matching .PRG overlay file for a PNB to extract its palette."""
    basename = os.path.splitext(pnb_name)[0]
    # Town maps like TOWN2.PNB or RUINSCR.PNB -> TWN_xxx.PRG? Usually they don't match exactly.
    # Often the prefix matches, e.g. FLD_A3.PNB -> FLD_A3.PRG
    # For now, look for exact basename match, or known fallback names
    prg_name = basename + '.PRG'
    
    if all_files is None:
        all_files = iso_reader.list_files()
        
    matches = [f for f in all_files if f['name'].upper() == prg_name.upper()]
    if matches:
        return matches[0]
        
    # Heuristics for non-matching names
    if "RUINSCR" in basename.upper():
        return next((f for f in all_files if f['name'].upper() == 'TWN_RUIN.PRG'), None)
    if "SEEKSCR" in basename.upper():
        return next((f for f in all_files if f['name'].upper() == 'TWN_SEEK.PRG'), None)
    if "ZOAH" in basename.upper():
        return next((f for f in all_files if f['name'].upper() == 'TWN_ZOAH.PRG'), None)
    if "TITLEE" in basename.upper() or "TITLE" in basename.upper():
        return next((f for f in all_files if f['name'].upper() == 'TITLE.PRG'), None)
    
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Extract VDP2 pattern name data from PDS .PNB files.'
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--iso', help='Path to disc image (.bin)')
    source.add_argument('--input', help='Path to a raw PNB file')

    parser.add_argument('--scb', help='Path to matching SCB file (raw file mode)')
    parser.add_argument('--palette', help='Path to raw RGB555 palette file (raw file mode)')
    parser.add_argument('--name', help='PNB filename on disc (e.g. ZOAH.PNB)')
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

        # Try to find SCB: explicit --scb, or auto-detect from same directory
        scb_data = None
        if args.scb:
            with open(args.scb, 'rb') as f:
                scb_data = f.read()
        else:
            basename = os.path.splitext(args.input)[0]
            scb_path = basename + '.SCB'
            if os.path.exists(scb_path):
                with open(scb_path, 'rb') as f:
                    scb_data = f.read()
                    
        palette_data = None
        if args.palette:
            with open(args.palette, 'rb') as f:
                palette_data = f.read()

        name = os.path.basename(args.input)
        if name.upper() in PALETTES_HARDCODED and not palette_data:
            palette_data = PALETTES_HARDCODED[name.upper()]
            
        count, analysis = extract_and_save(name, data, args.output, scb_data, palette_data)
        bpp = analysis.get('detected_bpp', '?')
        chars = analysis['unique_character_numbers']
        scb_msg = f", SCB assembled ({bpp}bpp)" if scb_data else ""
        pal_msg = " [colored]" if palette_data else " [greyscale]"
        print(f"  {name}: {count} entries, {chars} unique tiles{scb_msg}{pal_msg}")
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
        from collections import Counter
        size_counts = Counter(f['size'] for f in pnb_files)
        for f in sorted(pnb_files, key=lambda x: x['name']):
            entries = f['size'] // 2
            print(f"  {f['name']:30s}  {f['size']:>6d} bytes  "
                  f"({entries:>5d} entries)  LBA {f['lba']}")
        print(f"\nSize distribution:")
        for size, count in sorted(size_counts.items()):
            print(f"  {size:>6d} bytes ({size//2:>5d} entries): "
                  f"{count:>3d} files")
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
            iso.close()
            return
        pnb_files = matches

    elif not args.extract_all:
        print("Specify --extract-all to extract all PNB files, "
              "or --name to extract one.")
        print(f"Found {len(pnb_files)} PNB file(s). Use --list to list them.")
        iso.close()
        return

    os.makedirs(args.output, exist_ok=True)
    all_files = iso.list_files()
    print(f"Extracting {len(pnb_files)} PNB file(s)...\n")

    total_entries = 0
    errors = 0
    for finfo in sorted(pnb_files, key=lambda x: x['name']):
        data = iso.extract_file(finfo['lba'], finfo['size'])
        name = os.path.basename(finfo['name']).upper()

        # Find matching SCB
        scb_data = None
        scb_info = find_scb_file(iso, name, all_files)
        if scb_info:
            scb_data = iso.extract_file(scb_info['lba'], scb_info['size'])
            
        # Find matching Palette
        palette_data = None
        prg_info = find_prg_file(iso, name, all_files)
        if prg_info:
            prg_data = iso.extract_file(prg_info['lba'], prg_info['size'])
            
            # The pattern is consistently starting at 0x278 in these files.
            # Minimum block we care about is 512 bytes (256 colors for 8bpp).
            if len(prg_data) >= 0x278 + 512:
                palette_data = prg_data[0x278:]

        try:
            count, analysis = extract_and_save(name, data, args.output, scb_data, palette_data)
            chars = analysis['unique_character_numbers']
            maxc = analysis['max_character_number']
            bpp = analysis.get('detected_bpp', '?')
            scb_msg = f" SCB:{bpp}bpp" if scb_data else " (no SCB)"
            pal_msg = " +Pal" if palette_data else " (grey)"
            print(f"  {name:20s}  {count:>5d} entries  "
                  f"tiles={chars:>5d}  maxchar={maxc:>4d}{scb_msg}{pal_msg}")
            total_entries += count
        except Exception as e:
            print(f"  {name:20s}  ERROR: {e}")
            errors += 1

    iso.close()
    print(f"\nDone. {len(pnb_files) - errors} files extracted, "
          f"{total_entries} total entries. Output in {args.output}")
    if errors:
        print(f"  {errors} error(s) encountered.")


if __name__ == '__main__':
    main()
