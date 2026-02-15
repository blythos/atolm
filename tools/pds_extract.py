#!/usr/bin/env python3
"""
Panzer Dragoon Saga — MCB/CGB Asset Extractor

Extracts 3D models from a PDS disc image into three separate files per model:
  - {name}_model.json  — Geometry (quads, vertices, hierarchy, poses) 
  - {name}_anim.json   — Animation data (raw track data for viewer to simulate)
  - {name}_tex.png     — Texture atlas with all decoded textures

No proprietary game data is embedded — the tool reads from the disc at runtime.

Usage:
  python pds_extract.py disc.bin --list                    # List all MCB/CGB pairs
  python pds_extract.py disc.bin --extract DRAGON0          # Extract one model
  python pds_extract.py disc.bin --extract-all -o output/   # Extract everything
"""

import struct, sys, os, json, math, argparse
from io import BytesIO

# ── ISO9660 Reader ──────────────────────────────────────────────────────────

SECTOR_SIZE = 2352
HEADER_SIZE = 16
DATA_SIZE = 2048

def read_sector(f, sector_num):
    f.seek(sector_num * SECTOR_SIZE)
    raw = f.read(SECTOR_SIZE)
    if len(raw) < SECTOR_SIZE:
        return b'\x00' * DATA_SIZE
    return raw[HEADER_SIZE:HEADER_SIZE + DATA_SIZE]

def read_file_from_disc(f, sector, size):
    data = bytearray()
    remaining = size
    s = sector
    while remaining > 0:
        chunk = read_sector(f, s)
        take = min(remaining, DATA_SIZE)
        data.extend(chunk[:take])
        remaining -= take
        s += 1
    return bytes(data)

def parse_iso_directory(f):
    """Parse ISO9660 root directory, return dict of {filename: (sector, size)}"""
    pvd = read_sector(f, 16)
    root_entry = pvd[156:156+34]
    root_sector = struct.unpack('<I', root_entry[2:6])[0]
    root_size = struct.unpack('<I', root_entry[10:14])[0]
    
    dir_data = bytearray()
    for i in range((root_size + DATA_SIZE - 1) // DATA_SIZE):
        dir_data.extend(read_sector(f, root_sector + i))
    
    files = {}
    pos = 0
    while pos < root_size:
        rec_len = dir_data[pos]
        if rec_len == 0:
            pos = ((pos // DATA_SIZE) + 1) * DATA_SIZE
            continue
        name_len = dir_data[pos + 32]
        name = dir_data[pos+33:pos+33+name_len].decode('ascii', errors='replace')
        if ';' in name:
            name = name.split(';')[0]
        sector = struct.unpack('<I', dir_data[pos+2:pos+6])[0]
        size = struct.unpack('<I', dir_data[pos+10:pos+14])[0]
        if name_len > 0 and name not in ('.', '..', '\x00', '\x01'):
            files[name] = (sector, size)
        pos += rec_len
    return files

# ── Binary helpers ──────────────────────────────────────────────────────────

def ru32(d, o): return struct.unpack_from('>I', d, o)[0]
def rs32(d, o): return struct.unpack_from('>i', d, o)[0]
def ru16(d, o): return struct.unpack_from('>H', d, o)[0]
def rs16(d, o): return struct.unpack_from('>h', d, o)[0]

# ── MCB Parser ──────────────────────────────────────────────────────────────

def parse_pointer_table(mcb):
    """Parse the MCB pointer table. Returns list of offsets."""
    ptrs = []
    min_target = len(mcb)
    i = 0
    while i * 4 < min_target and i * 4 + 4 <= len(mcb):
        p = ru32(mcb, i * 4)
        if p == 0:
            ptrs.append(0)
        elif 0 < p < len(mcb):
            ptrs.append(p)
            min_target = min(min_target, p)
        else:
            break
        i += 1
    return ptrs

def classify_entries(mcb, ptrs):
    """Classify pointer table entries as model/hierarchy/pose/animation."""
    classified = []
    for idx, p in enumerate(ptrs):
        if p == 0:
            classified.append(('zero', idx, p))
            continue
        if p + 12 > len(mcb):
            classified.append(('unknown', idx, p))
            continue
        
        w0 = ru32(mcb, p)
        w1 = ru32(mcb, p + 4) if p + 8 <= len(mcb) else 0
        w2 = ru32(mcb, p + 8) if p + 12 <= len(mcb) else 0
        
        # Model check: w0=radius, w1=vertex count (1-5000), w2=vertex offset
        is_model = False
        if 1 <= w1 <= 5000 and 0 < w2 < len(mcb) and w2 + w1 * 6 <= len(mcb):
            is_model = True
        
        # Hierarchy check: chain of 12-byte nodes
        is_hier = False
        if p + 12 <= len(mcb):
            valid = True
            count = 0
            np = p
            while np + 12 <= len(mcb) and count < 200:
                m, c, s = ru32(mcb, np), ru32(mcb, np+4), ru32(mcb, np+8)
                if m == 0 and c == 0 and s == 0:
                    break
                if (m != 0 and m >= len(mcb)) or (c != 0 and c >= len(mcb)) or (s != 0 and s >= len(mcb)):
                    valid = False
                    break
                count += 1
                np += 12
            if valid and count >= 2:
                is_hier = True
        
        if is_model:
            classified.append(('model', idx, p))
        elif is_hier:
            classified.append(('hierarchy', idx, p))
        else:
            classified.append(('unknown', idx, p))
    
    return classified

def parse_model(mcb, offset):
    """Parse a 3D model sub-resource. Returns vertices and quads."""
    radius = rs32(mcb, offset)
    num_verts = ru32(mcb, offset + 4)
    vert_offset = ru32(mcb, offset + 8)
    
    if num_verts > 10000 or vert_offset + num_verts * 6 > len(mcb):
        return None
    
    # Vertices: s16 × 3, 12.4 fixed point → divide by 16
    vertices = []
    for i in range(num_verts):
        vo = vert_offset + i * 6
        x = rs16(mcb, vo)
        y = rs16(mcb, vo + 2)
        z = rs16(mcb, vo + 4)
        vertices.append([x, y, z])  # Keep raw s16 values
    
    # Quads: 20 bytes + lighting data
    quads = []
    qp = offset + 0x0C
    while qp + 20 <= len(mcb):
        i0 = ru16(mcb, qp)
        i1 = ru16(mcb, qp + 2)
        i2 = ru16(mcb, qp + 4)
        i3 = ru16(mcb, qp + 6)
        
        if i0 == 0 and i1 == 0 and i2 == 0 and i3 == 0:
            break
        
        # Validate indices
        if any(idx >= num_verts for idx in [i0, i1, i2, i3]):
            break
        
        lighting_ctrl = ru16(mcb, qp + 8)
        cmdctrl = ru16(mcb, qp + 10)
        cmdpmod = ru16(mcb, qp + 12)
        cmdcolr = ru16(mcb, qp + 14)
        cmdsrca = ru16(mcb, qp + 16)
        cmdsize = ru16(mcb, qp + 18)
        
        lm = (lighting_ctrl >> 8) & 3
        tex_w = (cmdsize & 0x3F00) >> 5
        tex_h = cmdsize & 0xFF
        color_mode = (cmdpmod >> 3) & 7
        flip_h = (cmdctrl >> 4) & 1
        flip_v = (cmdctrl >> 5) & 1
        spd = (cmdpmod >> 6) & 1  # Transparent pixel disable
        
        quad = {
            'indices': [i0, i1, i2, i3],
            'lightingMode': lm,
            'colorMode': color_mode,
            'texW': tex_w,
            'texH': tex_h,
            'cmdsrca': cmdsrca,
            'cmdcolr': cmdcolr,
            'cmdpmod': cmdpmod,
            'flipH': flip_h,
            'flipV': flip_v,
            'spd': spd,
        }
        
        # Read lighting extra data
        extra_size = [0, 8, 48, 24][lm]
        lighting_data = []
        if lm >= 1 and qp + 20 + extra_size <= len(mcb):
            ld_off = qp + 20
            if lm == 1:
                # Single normal (3 × s16 + 1 padding)
                nx = rs16(mcb, ld_off)
                ny = rs16(mcb, ld_off + 2)
                nz = rs16(mcb, ld_off + 4)
                lighting_data = [{'normal': [nx, ny, nz]}]
            elif lm == 2:
                # 4 × (normal + color): 4 × (3×s16 normal + 3×u16 color) = 48 bytes
                for vi in range(4):
                    vo2 = ld_off + vi * 12
                    nx = rs16(mcb, vo2)
                    ny = rs16(mcb, vo2 + 2)
                    nz = rs16(mcb, vo2 + 4)
                    cr = ru16(mcb, vo2 + 6)
                    cg = ru16(mcb, vo2 + 8)
                    cb = ru16(mcb, vo2 + 10)
                    lighting_data.append({'normal': [nx, ny, nz], 'color': [cr, cg, cb]})
            elif lm == 3:
                # 4 × normal: 4 × (3×s16) = 24 bytes
                for vi in range(4):
                    vo2 = ld_off + vi * 6
                    nx = rs16(mcb, vo2)
                    ny = rs16(mcb, vo2 + 2)
                    nz = rs16(mcb, vo2 + 4)
                    lighting_data.append({'normal': [nx, ny, nz]})
        
        if lighting_data:
            quad['lighting'] = lighting_data
        
        quads.append(quad)
        qp += 20 + extra_size
    
    return {'radius': radius, 'vertices': vertices, 'quads': quads}

def parse_hierarchy(mcb, offset):
    """Parse hierarchy tree. Returns list of nodes in traversal order and bone count."""
    nodes = []
    
    def walk(off, depth=0):
        if off == 0 or off >= len(mcb) or off + 12 > len(mcb):
            return
        model_off = ru32(mcb, off)
        child_off = ru32(mcb, off + 4)
        sibling_off = ru32(mcb, off + 8)
        
        node_idx = len(nodes)
        nodes.append({
            'offset': off,
            'modelOffset': model_off if model_off != 0 and model_off < len(mcb) else 0,
            'childOffset': child_off if child_off != 0 and child_off < len(mcb) else 0,
            'siblingOffset': sibling_off if sibling_off != 0 and sibling_off < len(mcb) else 0,
            'depth': depth,
        })
        
        if child_off != 0 and child_off < len(mcb):
            walk(child_off, depth + 1)
        if sibling_off != 0 and sibling_off < len(mcb):
            walk(sibling_off, depth)
    
    walk(offset)
    return nodes

def count_bones_recursive(mcb, offset):
    """Count bones exactly like yaz0r: 1 + subNode.count + nextNode.count"""
    if offset == 0 or offset >= len(mcb) or offset + 12 > len(mcb):
        return 0
    child_off = ru32(mcb, offset + 4)
    sibling_off = ru32(mcb, offset + 8)
    
    count = 1
    if child_off != 0 and child_off < len(mcb):
        count += count_bones_recursive(mcb, child_off)
    if sibling_off != 0 and sibling_off < len(mcb):
        count += count_bones_recursive(mcb, sibling_off)
    return count

def find_pose_data(mcb, ptrs, num_bones):
    """Find static pose data matching a bone count. Returns list of poses."""
    poses = []
    for idx, p in enumerate(ptrs):
        if p == 0 or p + num_bones * 36 > len(mcb):
            continue
        # Check if this looks like pose data: all scale fields ≈ 0x10000
        valid = True
        for b in range(num_bones):
            boff = p + b * 36
            sx = rs32(mcb, boff + 24)
            sy = rs32(mcb, boff + 28)
            sz = rs32(mcb, boff + 32)
            if not all(0x8000 <= v <= 0x18000 for v in [sx, sy, sz]):
                valid = False
                break
        if valid:
            # Parse pose data
            bones = []
            for b in range(num_bones):
                boff = p + b * 36
                tx = rs32(mcb, boff)
                ty = rs32(mcb, boff + 4)
                tz = rs32(mcb, boff + 8)
                rx = rs32(mcb, boff + 12)
                ry = rs32(mcb, boff + 16)
                rz = rs32(mcb, boff + 20)
                sx = rs32(mcb, boff + 24)
                sy = rs32(mcb, boff + 28)
                sz = rs32(mcb, boff + 32)
                bones.append({
                    'translation': [tx, ty, tz],  # 16.16 FP
                    'rotation': [rx, ry, rz],      # 16.16 FP (integer part is 12-bit angle)
                    'scale': [sx, sy, sz],          # 16.16 FP (1.0 = 0x10000)
                })
            poses.append({'entryIndex': idx, 'offset': p, 'bones': bones})
    return poses

def find_animations(mcb, ptrs, classified):
    """Find animation entries. Returns list of animation metadata."""
    animations = []
    for idx, p in enumerate(ptrs):
        if p == 0 or p + 12 > len(mcb):
            continue
        # Skip entries already classified as model/hierarchy
        entry_type = None
        for c in classified:
            if c[1] == idx:
                entry_type = c[0]
                break
        if entry_type in ('model', 'hierarchy'):
            continue
        
        # Check animation header: flags(u16), numBones(u16), numFrames(u16), pad(u16), trackHeaderOffset(u32)
        flags = ru16(mcb, p)
        if flags == 0:
            continue
        
        mode = flags & 7
        if mode not in (0, 1, 4, 5):
            continue
        
        num_bones = ru16(mcb, p + 2)
        num_frames = ru16(mcb, p + 4)
        
        if num_bones == 0 or num_bones > 100 or num_frames == 0 or num_frames > 500:
            continue
        
        track_header_off = ru32(mcb, p + 8)
        if track_header_off == 0 or p + track_header_off >= len(mcb):
            continue
        
        # Validate track header structure: each bone has 9×s16 lengths + 2 pad + 9×u32 offsets = 0x38 bytes
        abs_track = p + track_header_off
        if abs_track + num_bones * 0x38 > len(mcb):
            continue
        
        # Looks like valid animation data
        animations.append({
            'entryIndex': idx,
            'offset': p,
            'flags': flags,
            'mode': mode,
            'numBones': num_bones,
            'numFrames': num_frames,
            'hasPosition': bool(flags & 8),
            'hasRotation': bool(flags & 0x10),
            'hasScale': bool(flags & 0x20),
        })
    
    return animations

def extract_animation_tracks(mcb, anim_offset, num_bones):
    """Extract raw animation track data for a single animation.
    
    Returns per-bone track data: 9 tracks (tx,ty,tz,rx,ry,rz,sx,sy,sz),
    each track is a list of s16 values.
    """
    base = anim_offset
    track_header_off = ru32(mcb, base + 8)
    
    all_bones = []
    for bi in range(num_bones):
        th_off = base + track_header_off + 0x38 * bi
        
        # Read 9 track lengths (s16)
        lengths = []
        for i in range(9):
            lengths.append(rs16(mcb, th_off + i * 2))
        
        # Skip 2 bytes padding
        # Read 9 track data offsets (u32)
        offsets = []
        for i in range(9):
            offsets.append(ru32(mcb, th_off + 20 + i * 4))
        
        # Read track data for each channel
        tracks = []
        for ch in range(9):
            vals = []
            if lengths[ch] > 0 and offsets[ch] > 0:
                abs_off = base + offsets[ch]
                for j in range(lengths[ch]):
                    if abs_off + j * 2 + 2 <= len(mcb):
                        vals.append(rs16(mcb, abs_off + j * 2))
                    else:
                        vals.append(0)
            tracks.append(vals)
        
        all_bones.append(tracks)
    
    return all_bones

# ── Texture Decoder ─────────────────────────────────────────────────────────

def decode_rgb555(raw_u16):
    """Saturn ABGR1555 → RGBA. R=bits 0-4, G=bits 5-9, B=bits 10-14, MSB=bit 15."""
    r = (raw_u16 & 0x1F) << 3
    g = ((raw_u16 >> 5) & 0x1F) << 3
    b = ((raw_u16 >> 10) & 0x1F) << 3
    a = 255
    return (r, g, b, a)

def decode_texture(cgb, cmdsrca, cmdcolr, cmdpmod, tex_w, tex_h, spd):
    """Decode a single texture from CGB data. Returns RGBA pixel list or None."""
    if tex_w == 0 or tex_h == 0:
        return None
    
    color_mode = (cmdpmod >> 3) & 7
    tex_offset = cmdsrca * 8
    pixels = []
    
    if color_mode == 5:
        # 16bpp direct RGB555
        for y in range(tex_h):
            for x in range(tex_w):
                addr = tex_offset + (y * tex_w + x) * 2
                if addr + 2 <= len(cgb):
                    raw = struct.unpack_from('>H', cgb, addr)[0]
                    if raw == 0 and not spd:
                        pixels.append((0, 0, 0, 0))  # Transparent
                    else:
                        pixels.append(decode_rgb555(raw))
                else:
                    pixels.append((0, 0, 0, 0))
    
    elif color_mode == 1:
        # 4bpp LUT mode — palette at CMDCOLR×8 in CGB
        lut_offset = cmdcolr * 8
        palette = []
        for i in range(16):
            if lut_offset + i * 2 + 2 <= len(cgb):
                raw = struct.unpack_from('>H', cgb, lut_offset + i * 2)[0]
                palette.append(raw)
            else:
                palette.append(0)
        
        for y in range(tex_h):
            for x in range(tex_w):
                byte_addr = tex_offset + (y * tex_w + x) // 2
                if byte_addr < len(cgb):
                    byte_val = cgb[byte_addr]
                    if (y * tex_w + x) % 2 == 0:
                        nibble = (byte_val >> 4) & 0xF
                    else:
                        nibble = byte_val & 0xF
                    
                    if nibble == 0 and not spd:
                        pixels.append((0, 0, 0, 0))
                    else:
                        raw = palette[nibble]
                        if raw & 0x8000:
                            pixels.append(decode_rgb555(raw))
                        elif raw != 0:
                            # Non-MSB, non-zero: treated as shadow/special
                            pixels.append((0, 0, 0, 0))
                        else:
                            pixels.append((0, 0, 0, 0))
                else:
                    pixels.append((0, 0, 0, 0))
    
    elif color_mode == 0:
        # 4bpp bank mode — needs VDP2 Color RAM (PNB)
        # Fallback: greyscale based on nibble value
        for y in range(tex_h):
            for x in range(tex_w):
                byte_addr = tex_offset + (y * tex_w + x) // 2
                if byte_addr < len(cgb):
                    byte_val = cgb[byte_addr]
                    if (y * tex_w + x) % 2 == 0:
                        nibble = (byte_val >> 4) & 0xF
                    else:
                        nibble = byte_val & 0xF
                    if nibble == 0 and not spd:
                        pixels.append((0, 0, 0, 0))
                    else:
                        g = nibble * 17  # 0-255
                        pixels.append((g, g, g, 255))
                else:
                    pixels.append((0, 0, 0, 0))
    
    elif color_mode == 4:
        # 8bpp bank mode — needs VDP2 Color RAM
        # Fallback: greyscale
        for y in range(tex_h):
            for x in range(tex_w):
                addr = tex_offset + y * tex_w + x
                if addr < len(cgb):
                    val = cgb[addr]
                    if val == 0 and not spd:
                        pixels.append((0, 0, 0, 0))
                    else:
                        pixels.append((val, val, val, 255))
                else:
                    pixels.append((0, 0, 0, 0))
    
    else:
        return None
    
    return pixels

def build_texture_atlas(mcb, cgb, models):
    """Build a texture atlas from all unique textures across all models.
    
    Returns: (atlas_pixels, atlas_width, atlas_height, texture_map)
    where texture_map maps (cmdsrca, cmdcolr, cmdpmod, cmdsize) → (x, y, w, h) in atlas
    """
    # Collect unique textures
    unique_textures = {}  # key → (w, h, pixels)
    
    for model in models:
        if model is None:
            continue
        for quad in model['quads']:
            key = (quad['cmdsrca'], quad['cmdcolr'], quad['cmdpmod'], quad['texW'], quad['texH'])
            if key in unique_textures or quad['texW'] == 0 or quad['texH'] == 0:
                continue
            
            pixels = decode_texture(cgb, quad['cmdsrca'], quad['cmdcolr'], 
                                   quad['cmdpmod'], quad['texW'], quad['texH'], quad['spd'])
            if pixels:
                unique_textures[key] = (quad['texW'], quad['texH'], pixels)
    
    if not unique_textures:
        return None, 0, 0, {}
    
    # Layout: stack textures vertically
    atlas_w = max(w for w, h, p in unique_textures.values())
    atlas_h = sum(h for w, h, p in unique_textures.values())
    atlas = [(0, 0, 0, 0)] * (atlas_w * atlas_h)
    
    tex_map = {}
    y_cursor = 0
    for key, (tw, th, pixels) in unique_textures.items():
        for ty in range(th):
            for tx in range(tw):
                atlas[(y_cursor + ty) * atlas_w + tx] = pixels[ty * tw + tx]
        tex_map[key] = (0, y_cursor, tw, th)
        y_cursor += th
    
    return atlas, atlas_w, atlas_h, tex_map

def save_atlas_png(atlas_pixels, width, height, filepath):
    """Save atlas as PNG. Uses pure Python PNG writer to avoid PIL dependency."""
    import zlib
    
    def write_chunk(f, chunk_type, data):
        f.write(struct.pack('>I', len(data)))
        f.write(chunk_type)
        f.write(data)
        crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        f.write(struct.pack('>I', crc))
    
    with open(filepath, 'wb') as f:
        # PNG signature
        f.write(b'\x89PNG\r\n\x1a\n')
        
        # IHDR
        ihdr = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
        write_chunk(f, b'IHDR', ihdr)
        
        # IDAT — raw pixel data with filter byte per row
        raw_data = bytearray()
        for y in range(height):
            raw_data.append(0)  # No filter
            for x in range(width):
                r, g, b, a = atlas_pixels[y * width + x]
                raw_data.extend([r, g, b, a])
        
        compressed = zlib.compress(bytes(raw_data), 9)
        write_chunk(f, b'IDAT', compressed)
        
        # IEND
        write_chunk(f, b'IEND', b'')

# ── Main Extraction ─────────────────────────────────────────────────────────

def extract_model(name, mcb, cgb, output_dir, verbose=False):
    """Extract a single MCB/CGB pair into model, animation, and texture files."""
    
    ptrs = parse_pointer_table(mcb)
    classified = classify_entries(mcb, ptrs)
    
    # Find all hierarchies, models, and their relationships
    hierarchies = []
    model_entries = []
    
    for entry_type, idx, offset in classified:
        if entry_type == 'hierarchy':
            nodes = parse_hierarchy(mcb, offset)
            bone_count = count_bones_recursive(mcb, offset)
            hierarchies.append({
                'entryIndex': idx,
                'offset': offset,
                'nodes': nodes,
                'boneCount': bone_count,
            })
        elif entry_type == 'model':
            model_entries.append((idx, offset))
    
    # Parse all models
    models = {}
    for idx, offset in model_entries:
        model = parse_model(mcb, offset)
        if model:
            models[offset] = model
            models[offset]['entryIndex'] = idx
    
    # Find pose data for each hierarchy
    all_poses = []
    for hier in hierarchies:
        poses = find_pose_data(mcb, ptrs, hier['boneCount'])
        all_poses.extend(poses)
    
    # Find animations
    animations = find_animations(mcb, ptrs, classified)
    
    # Extract animation track data
    anim_data_list = []
    for anim in animations:
        tracks = extract_animation_tracks(mcb, anim['offset'], anim['numBones'])
        anim_data_list.append({
            'entryIndex': anim['entryIndex'],
            'flags': anim['flags'],
            'mode': anim['mode'],
            'numBones': anim['numBones'],
            'numFrames': anim['numFrames'],
            'hasPosition': anim['hasPosition'],
            'hasRotation': anim['hasRotation'],
            'hasScale': anim['hasScale'],
            'tracks': tracks,  # [bone][channel] → [s16 values]
        })
    
    # Build texture atlas
    all_models = [m for m in models.values()]
    atlas, atlas_w, atlas_h, tex_map = build_texture_atlas(mcb, cgb, all_models) if cgb else (None, 0, 0, {})
    
    # ── Write model JSON ──
    # Map model offsets to indices for hierarchy references
    model_offset_to_idx = {}
    model_list = []
    for i, (offset, model) in enumerate(sorted(models.items())):
        model_offset_to_idx[offset] = i
        model_list.append({
            'index': i,
            'entryIndex': model['entryIndex'],
            'radius': model['radius'],
            'vertices': model['vertices'],  # Raw s16 values (12.4 FP)
            'quads': model['quads'],
        })
    
    # Build hierarchy with model index references
    hier_list = []
    for hier in hierarchies:
        nodes_out = []
        for node in hier['nodes']:
            model_idx = model_offset_to_idx.get(node['modelOffset'], -1)
            nodes_out.append({
                'modelIndex': model_idx,
                'hasChild': node['childOffset'] != 0,
                'hasSibling': node['siblingOffset'] != 0,
                'depth': node['depth'],
            })
        hier_list.append({
            'entryIndex': hier['entryIndex'],
            'boneCount': hier['boneCount'],
            'nodes': nodes_out,
        })
    
    # Build texture map for JSON (convert tuple keys to string keys)
    tex_map_json = {}
    for (cmdsrca, cmdcolr, cmdpmod, tw, th), (ax, ay, aw, ah) in tex_map.items():
        key = f"{cmdsrca}_{cmdcolr}_{cmdpmod}_{tw}_{th}"
        tex_map_json[key] = {'x': ax, 'y': ay, 'w': aw, 'h': ah}
    
    model_json = {
        'name': name,
        'models': model_list,
        'hierarchies': hier_list,
        'poses': all_poses,
        'atlasWidth': atlas_w,
        'atlasHeight': atlas_h,
        'textureMap': tex_map_json,
    }
    
    os.makedirs(output_dir, exist_ok=True)
    
    model_path = os.path.join(output_dir, f'{name}_model.json')
    with open(model_path, 'w') as f:
        json.dump(model_json, f)
    
    # ── Write animation JSON ──
    anim_json = {
        'name': name,
        'animations': anim_data_list,
    }
    
    anim_path = os.path.join(output_dir, f'{name}_anim.json')
    with open(anim_path, 'w') as f:
        json.dump(anim_json, f)
    
    # ── Write texture atlas PNG ──
    tex_path = os.path.join(output_dir, f'{name}_tex.png')
    if atlas and atlas_w > 0 and atlas_h > 0:
        save_atlas_png(atlas, atlas_w, atlas_h, tex_path)
    else:
        # Write a 1x1 transparent PNG as placeholder
        save_atlas_png([(0, 0, 0, 0)], 1, 1, tex_path)
    
    if verbose:
        print(f"  {name}: {len(model_list)} models, {len(hier_list)} hierarchies, "
              f"{len(all_poses)} poses, {len(anim_data_list)} animations, "
              f"atlas {atlas_w}x{atlas_h}")
    
    return {
        'models': len(model_list),
        'hierarchies': len(hier_list),
        'poses': len(all_poses),
        'animations': len(anim_data_list),
        'atlasSize': f'{atlas_w}x{atlas_h}',
    }

def categorize_name(name):
    """Categorize a model name for UI grouping."""
    n = name.upper()
    if n.startswith('DRAGON') or n.startswith('C_DRA') or n.startswith('RIDER'):
        return 'Dragons'
    if n in ('EDGE', 'AZEL'):
        return 'Characters'
    if n.startswith('FLD_'):
        return 'Fields'
    if n.startswith(('X_A_', 'X_E_', 'X_F_', 'X_G_', 'Z_A_', 'Z_B_', 'Z_E_', 'Z_F_')):
        return 'NPCs'
    if n.endswith('MP') or any(n.endswith(f'MP{i}') for i in range(10)):
        return 'Maps'
    return 'Other'

def main():
    parser = argparse.ArgumentParser(description='Panzer Dragoon Saga MCB/CGB Extractor')
    parser.add_argument('disc', help='Path to disc track image (.bin)')
    parser.add_argument('--list', action='store_true', help='List all MCB/CGB pairs')
    parser.add_argument('--extract', metavar='NAME', help='Extract a single model by name (without extension)')
    parser.add_argument('--extract-all', action='store_true', help='Extract all models')
    parser.add_argument('-o', '--output', default='extracted', help='Output directory')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    args = parser.parse_args()
    
    with open(args.disc, 'rb') as f:
        files = parse_iso_directory(f)
        
        # Find MCB/CGB pairs
        mcb_files = sorted([n for n in files if n.upper().endswith('.MCB')])
        cgb_files = {n.upper(): n for n in files if n.upper().endswith('.CGB')}
        
        pairs = []
        for mcb_name in mcb_files:
            base = mcb_name.rsplit('.', 1)[0]
            cgb_name = base + '.CGB'
            has_cgb = cgb_name.upper() in cgb_files
            pairs.append((base, mcb_name, cgb_files.get(cgb_name.upper()), has_cgb))
        
        if args.list:
            categories = {}
            for base, mcb_name, cgb_name, has_cgb in pairs:
                cat = categorize_name(base)
                if cat not in categories:
                    categories[cat] = []
                mcb_size = files[mcb_name][1]
                cgb_size = files[cgb_name][1] if cgb_name and cgb_name in files else 0
                categories[cat].append((base, mcb_size, cgb_size, has_cgb))
            
            for cat in sorted(categories.keys()):
                print(f"\n=== {cat} ({len(categories[cat])}) ===")
                for base, ms, cs, hc in categories[cat]:
                    cgb_info = f"CGB: {cs:>8d}" if hc else "no CGB"
                    print(f"  {base:20s}  MCB: {ms:>8d}  {cgb_info}")
            
            print(f"\nTotal: {len(pairs)} MCB files")
            return
        
        if args.extract:
            target = args.extract.upper()
            found = None
            for base, mcb_name, cgb_name, has_cgb in pairs:
                if base.upper() == target:
                    found = (base, mcb_name, cgb_name, has_cgb)
                    break
            
            if not found:
                print(f"Error: '{args.extract}' not found on disc")
                sys.exit(1)
            
            base, mcb_name, cgb_name, has_cgb = found
            mcb_sector, mcb_size = files[mcb_name]
            mcb_data = read_file_from_disc(f, mcb_sector, mcb_size)
            
            cgb_data = b''
            if has_cgb and cgb_name in files:
                cgb_sector, cgb_size = files[cgb_name]
                cgb_data = read_file_from_disc(f, cgb_sector, cgb_size)
            
            print(f"Extracting {base}...")
            result = extract_model(base, mcb_data, cgb_data, args.output, args.verbose)
            print(f"Done: {result}")
        
        elif args.extract_all:
            print(f"Extracting {len(pairs)} models to {args.output}/")
            
            # Write manifest
            manifest = {'models': [], 'categories': {}}
            
            for i, (base, mcb_name, cgb_name, has_cgb) in enumerate(pairs):
                mcb_sector, mcb_size = files[mcb_name]
                mcb_data = read_file_from_disc(f, mcb_sector, mcb_size)
                
                cgb_data = b''
                if has_cgb and cgb_name in files:
                    cgb_sector, cgb_size = files[cgb_name]
                    cgb_data = read_file_from_disc(f, cgb_sector, cgb_size)
                
                try:
                    result = extract_model(base, mcb_data, cgb_data, args.output, args.verbose)
                    cat = categorize_name(base)
                    entry = {'name': base, 'category': cat, 'hasCGB': has_cgb, **result}
                    manifest['models'].append(entry)
                    if cat not in manifest['categories']:
                        manifest['categories'][cat] = []
                    manifest['categories'][cat].append(base)
                    
                    print(f"  [{i+1}/{len(pairs)}] {base}: {result['models']}m {result['hierarchies']}h {result['animations']}a")
                except Exception as e:
                    print(f"  [{i+1}/{len(pairs)}] {base}: ERROR — {e}")
            
            manifest_path = os.path.join(args.output, 'manifest.json')
            with open(manifest_path, 'w') as mf:
                json.dump(manifest, mf, indent=2)
            
            print(f"\nDone. Manifest written to {manifest_path}")
        
        else:
            parser.print_help()

if __name__ == '__main__':
    main()
