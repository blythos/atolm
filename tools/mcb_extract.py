#!/usr/bin/env python3
"""
mcb_extract.py - Panzer Dragoon Saga MCB/CGB -> glTF Batch Extractor
=====================================================================

Extracts all 3D model assets from a PDS disc image to glTF 2.0 format (.glb).
Each MCB/CGB pair produces:
  - A .glb file: all mesh geometry, decoded textures, bone hierarchy
  - A .json sidecar: full asset metadata (hierarchies, poses, animations, unknown entries)

Handles:
  - Hierarchical models (dragons, characters, enemies): skeletal transform applied
  - Map bundles (*MP files): standalone models extracted at origin
  - Field geometry (FLD_*): hierarchical + standalone hybrid
  - MCB-only files: geometry without textures (collision meshes etc)

Texture modes supported:
  - Mode 1 (4bpp LUT): Full color via 16-entry palette in CGB
  - Mode 5 (16bpp RGB555): Direct color, Saturn ABGR1555
  - Mode 0 (4bpp bank): Greyscale fallback (needs PNB for true color)
  - Mode 4 (8bpp bank): Greyscale fallback (needs PNB for true color)

Animation data is exported as metadata in the glTF extras and as raw binary
blobs in the JSON sidecar (base64-encoded), enabling future keyframe decoding
without re-reading the disc image.

Usage:
    python mcb_extract.py <disc_image.bin> <output_dir> [options]

    --filter PATTERN   Only extract assets matching pattern (case-insensitive)
    --single NAME      Extract single asset by exact name
    --list             List all assets without extracting
    --verbose          Show detailed progress and errors
    --raw-anims        Include base64-encoded raw animation data in JSON sidecar

Part of the atolm project: https://github.com/blythos/atolm
"""

import struct, math, os, sys, json, argparse, io, base64
from pathlib import Path
import numpy as np
from PIL import Image

try:
    import pygltflib
    from pygltflib import (GLTF2, Scene, Node, Mesh, Primitive, Accessor,
                           BufferView, Buffer, Material, Texture, TextureInfo,
                           Sampler, FLOAT, UNSIGNED_INT, UNSIGNED_SHORT,
                           ELEMENT_ARRAY_BUFFER, ARRAY_BUFFER, TRIANGLES)
    from pygltflib import Image as GLTFImage
except ImportError:
    print("Error: pygltflib required.  pip install pygltflib --break-system-packages")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════════════
# Saturn binary readers (big-endian)
# ═══════════════════════════════════════════════════════════════════════════════

def read_u32(d, o): return struct.unpack('>I', d[o:o+4])[0]
def read_s32(d, o): return struct.unpack('>i', d[o:o+4])[0]
def read_u16(d, o): return struct.unpack('>H', d[o:o+2])[0]
def read_s16(d, o): return struct.unpack('>h', d[o:o+2])[0]

# ═══════════════════════════════════════════════════════════════════════════════
# ISO9660 reader (raw Mode 2 CD-ROM: 2352 bytes/sector)
# ═══════════════════════════════════════════════════════════════════════════════

SECTOR_SIZE = 2352
HEADER_SIZE = 16
DATA_SIZE = 2048

def read_sector(f, n):
    f.seek(n * SECTOR_SIZE)
    raw = f.read(SECTOR_SIZE)
    return raw[HEADER_SIZE:HEADER_SIZE + DATA_SIZE] if len(raw) >= SECTOR_SIZE else b'\x00' * DATA_SIZE

def read_file_from_disc(path, sector, size):
    nsec = (size + DATA_SIZE - 1) // DATA_SIZE
    data = bytearray()
    with open(path, 'rb') as f:
        for i in range(nsec):
            data.extend(read_sector(f, sector + i))
    return bytes(data[:size])

def parse_iso9660(track_path):
    """Parse root directory of ISO9660 filesystem from raw track image."""
    files = {}
    with open(track_path, 'rb') as f:
        pvd = read_sector(f, 16)
        re = pvd[156:156+34]
        root_sector = struct.unpack('<I', re[2:6])[0]
        root_size = struct.unpack('<I', re[10:14])[0]
        dd = bytearray()
        for i in range((root_size + DATA_SIZE - 1) // DATA_SIZE):
            dd.extend(read_sector(f, root_sector + i))
        pos = 0
        while pos < root_size:
            rl = dd[pos]
            if rl == 0:
                pos = ((pos // DATA_SIZE) + 1) * DATA_SIZE
                continue
            nl = dd[pos + 32]
            name = dd[pos+33:pos+33+nl].decode('ascii', errors='replace')
            if ';' in name:
                name = name.split(';')[0]
            sec = struct.unpack('<I', dd[pos+2:pos+6])[0]
            sz = struct.unpack('<I', dd[pos+10:pos+14])[0]
            if nl > 0 and name not in ('.', '..', '\x00', '\x01'):
                files[name] = (sec, sz)
            pos += rl
    return files

# ═══════════════════════════════════════════════════════════════════════════════
# MCB pointer table parser
# ═══════════════════════════════════════════════════════════════════════════════

def parse_ptrs(data):
    """Read the MCB pointer table: N × u32 offsets, ending where first target begins."""
    ptrs = []
    min_target = len(data)
    i = 0
    while i * 4 < min_target and i * 4 + 4 <= len(data):
        p = read_u32(data, i * 4)
        if p == 0:
            ptrs.append(0)
        elif 0 < p < len(data):
            ptrs.append(p)
            min_target = min(min_target, p)
        else:
            break
        i += 1
    return ptrs

# ═══════════════════════════════════════════════════════════════════════════════
# Hierarchy analysis
# ═══════════════════════════════════════════════════════════════════════════════

def count_bones(data, off, visited=None):
    """Recursively count bones in a hierarchy tree."""
    if visited is None:
        visited = set()
    if off == 0 or off in visited or off + 12 > len(data):
        return 0
    visited.add(off)
    child = read_u32(data, off + 4)
    sibling = read_u32(data, off + 8)
    return 1 + count_bones(data, child, visited) + count_bones(data, sibling, visited)

def is_hierarchy(data, ptrs, idx):
    """Test if pointer table entry points to a valid hierarchy node.
    
    A hierarchy node is 12 bytes: modelOffset, childOffset, siblingOffset.
    All three must be 0 or valid offsets within the MCB.
    Must have at least 2 bones (otherwise it's just a single model ref).
    The modelOffset, if non-zero, should point to something that looks like model data
    (i.e. the +4 field should be a small vertex count, not a huge number).
    """
    if idx >= len(ptrs) or ptrs[idx] == 0:
        return False
    off = ptrs[idx]
    if off + 12 > len(data):
        return False
    m_off = read_u32(data, off)
    c_off = read_u32(data, off + 4)
    s_off = read_u32(data, off + 8)
    # All values must be valid offsets or 0
    for v in [m_off, c_off, s_off]:
        if v != 0 and v >= len(data):
            return False
    # Can't be all zero
    if m_off == 0 and c_off == 0 and s_off == 0:
        return False
    # Must have at least 2 bones (otherwise single model pointer, not a tree)
    nb = count_bones(data, off)
    if nb < 2:
        return False
    # Extra check: if modelOffset is non-zero, verify it plausibly points to a model.
    # Model header: +0=radius, +4=numVerts (should be 1-10000), +8=vertOffset.
    # Hierarchy misclassification happens when model headers look like 3-pointer nodes.
    # If the "model" pointed to by the first node has nVerts=0 or absurdly large, reject.
    if m_off > 0 and m_off + 12 <= len(data):
        nv_check = read_u32(data, m_off + 4)
        if nv_check == 0 or nv_check > 10000:
            # First node's model pointer doesn't point to valid model data.
            # This might still be a real hierarchy if children have valid models.
            # Walk children and check at least one has a valid model.
            has_any_model = False
            def _check_tree(o, vis=None):
                nonlocal has_any_model
                if vis is None: vis = set()
                if o == 0 or o in vis or o + 12 > len(data): return
                vis.add(o)
                mo2 = read_u32(data, o)
                if mo2 > 0 and mo2 + 12 <= len(data):
                    nv2 = read_u32(data, mo2 + 4)
                    if 0 < nv2 <= 10000:
                        has_any_model = True
                        return
                _check_tree(read_u32(data, o + 4), vis)
                _check_tree(read_u32(data, o + 8), vis)
            _check_tree(off)
            if not has_any_model:
                return False
    return True

def is_model(data, ptrs, idx):
    """Test if pointer table entry points to a valid 3D model header."""
    if idx >= len(ptrs) or ptrs[idx] == 0:
        return False
    off = ptrs[idx]
    if off + 12 > len(data):
        return False
    nv = read_u32(data, off + 4)
    vo = read_u32(data, off + 8)
    if nv == 0 or nv > 10000:
        return False
    if vo + nv * 6 > len(data):
        return False
    # Vertex offset should be within data area, not in the pointer table
    if len(ptrs) > 0 and vo < ptrs[0] and ptrs[0] != 0:
        return False
    return True

# ═══════════════════════════════════════════════════════════════════════════════
# Pose data finder
# ═══════════════════════════════════════════════════════════════════════════════

def find_pose(data, ptrs, nb):
    """Find pose data for nb bones: N×36 bytes where all scale fields ≈ 1.0."""
    req = nb * 36
    for idx in range(len(ptrs)):
        if ptrs[idx] == 0:
            continue
        off = ptrs[idx]
        if off + req > len(data):
            continue
        ok = 0
        for b in range(nb):
            bo = off + b * 36
            if bo + 36 > len(data):
                break
            # Scale fields (bytes 24,28,32) should be close to 0x10000 (=1.0 in 16.16)
            if all(abs(read_s32(data, bo + j) - 0x10000) < 0x8000 for j in [24, 28, 32]):
                ok += 1
        if ok == nb:
            return idx, off
    return None, None

FP = 1.0 / 4096.0  # Combined 12.4 vertex → 16.16 bone space → display scale

def parse_pose(data, off, nb):
    """Parse N×36-byte static pose data."""
    bones = []
    for b in range(nb):
        bo = off + b * 36
        bones.append({
            't': (read_s32(data, bo) * FP,
                  read_s32(data, bo + 4) * FP,
                  read_s32(data, bo + 8) * FP),
            'r': tuple(read_s32(data, bo + 12 + j * 4) / 65536.0 * 2 * math.pi for j in range(3)),
            's': tuple(read_s32(data, bo + 24 + j * 4) / 65536.0 for j in range(3)),
        })
    return bones

# ═══════════════════════════════════════════════════════════════════════════════
# Animation finder
# ═══════════════════════════════════════════════════════════════════════════════

def find_anims(data, ptrs, pose_idx, nb):
    """Find animation entries after pose data.
    
    Animation header (heuristic):
      u16 flags (≤0x40), u16 numBones (matches hierarchy), 
      u16 numFrames (1-9999), ...
    """
    anims = []
    if pose_idx is None:
        return anims
    for idx in range(pose_idx + 1, len(ptrs)):
        if ptrs[idx] == 0:
            continue
        off = ptrs[idx]
        if off + 8 > len(data):
            continue
        v0 = read_u32(data, off)
        v1 = read_u32(data, off + 4)
        flags = (v0 >> 16) & 0xFFFF
        anim_bones = v0 & 0xFFFF
        anim_frames = (v1 >> 16) & 0xFFFF
        if 0 < anim_bones <= 50 and 0 < anim_frames < 10000 and flags <= 0x40:
            # Calculate size (up to next pointer entry)
            nxt = len(data)
            for j in range(idx + 1, len(ptrs)):
                if ptrs[j] != 0:
                    nxt = ptrs[j]
                    break
            anims.append({
                'ptr_index': idx, 'offset': off, 'flags': flags,
                'num_bones': anim_bones, 'num_frames': anim_frames,
                'size': nxt - off
            })
    return anims

# ═══════════════════════════════════════════════════════════════════════════════
# Matrix math
# ═══════════════════════════════════════════════════════════════════════════════

def rot_zyx(rx, ry, rz):
    """Create 4x4 rotation matrix with ZYX order (Z first, then Y, then X)."""
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    m = np.eye(4)
    m[0][0] = cy * cz;  m[0][1] = cy * sz;       m[0][2] = -sy
    m[1][0] = sx*sy*cz - cx*sz;  m[1][1] = sx*sy*sz + cx*cz;  m[1][2] = sx * cy
    m[2][0] = cx*sy*cz + sx*sz;  m[2][1] = cx*sy*sz - sx*cz;  m[2][2] = cx * cy
    return m

def walk_hier(data, off, pose, parent_mat=None, bone_idx=None):
    """Walk hierarchy tree applying skeletal transforms.
    
    Engine traversal: for each node:
      push matrix → translate → rotateZYX → draw model → recurse children → pop → continue siblings
    
    Returns: list of (model_offset, world_matrix, bone_index) tuples
    """
    if parent_mat is None:
        parent_mat = np.eye(4)
    if bone_idx is None:
        bone_idx = [0]
    result = []
    while True:
        b = bone_idx[0]
        if b >= len(pose) or off == 0 or off + 12 > len(data):
            return result
        bone = pose[b]
        m_off = read_u32(data, off)
        c_off = read_u32(data, off + 4)
        s_off = read_u32(data, off + 8)
        # Build local transform: translate then rotate ZYX
        T = np.eye(4)
        T[0][3], T[1][3], T[2][3] = bone['t']
        R = rot_zyx(*bone['r'])
        cur = parent_mat @ T @ R
        if m_off > 0 and m_off + 12 <= len(data):
            result.append((m_off, cur.copy(), b))
        if c_off > 0:
            bone_idx[0] += 1
            result.extend(walk_hier(data, c_off, pose, cur, bone_idx))
        if s_off == 0:
            return result
        bone_idx[0] += 1
        off = s_off

# ═══════════════════════════════════════════════════════════════════════════════
# 3D Model parser
# ═══════════════════════════════════════════════════════════════════════════════

def parse_model(data, moff):
    """Parse a 3D model sub-resource at the given offset.
    
    Returns dict with 'verts' list and 'quads' list, or None if invalid.
    """
    if moff + 12 > len(data):
        return None
    nv = read_u32(data, moff + 4)
    vo = read_u32(data, moff + 8)
    if nv == 0 or nv > 10000 or vo + nv * 6 > len(data):
        return None
    # Parse vertices: 3 × s16, fixed-point 12.4 (×16 into 16.16 space, then ÷4096 for display)
    verts = []
    for v in range(nv):
        verts.append((
            read_s16(data, vo + v * 6) * 16 * FP,
            read_s16(data, vo + v * 6 + 2) * 16 * FP,
            read_s16(data, vo + v * 6 + 4) * 16 * FP
        ))
    # Parse quads (20 bytes each + lighting data, terminated by all-zero indices)
    quads = []
    qoff = moff + 0x0C
    while qoff + 20 <= len(data):
        i0 = read_u16(data, qoff)
        i1 = read_u16(data, qoff + 2)
        i2 = read_u16(data, qoff + 4)
        i3 = read_u16(data, qoff + 6)
        if i0 == 0 and i1 == 0 and i2 == 0 and i3 == 0:
            break
        if max(i0, i1, i2, i3) >= nv:
            break
        lctrl = read_u16(data, qoff + 8)
        cmdctrl = read_u16(data, qoff + 10)
        cmdpmod = read_u16(data, qoff + 12)
        cmdcolr = read_u16(data, qoff + 14)
        cmdsrca = read_u16(data, qoff + 16)
        cmdsize = read_u16(data, qoff + 18)
        lm = (lctrl >> 8) & 3
        qoff += 20
        # Skip lighting mode extra data
        if lm == 1: qoff += 8
        elif lm == 2: qoff += 48
        elif lm == 3: qoff += 24
        quads.append({
            'idx': (i0, i1, i2, i3),
            'cmdpmod': cmdpmod, 'cmdcolr': cmdcolr,
            'cmdsrca': cmdsrca, 'cmdsize': cmdsize,
            'color_mode': (cmdpmod >> 3) & 7,
            'tex_w': (cmdsize & 0x3F00) >> 5,
            'tex_h': cmdsize & 0xFF,
            'flip_h': bool(cmdctrl & 0x10),
            'flip_v': bool(cmdctrl & 0x20),
            'spd': bool(cmdpmod & 0x40),
        })
    return {'verts': verts, 'quads': quads}

# ═══════════════════════════════════════════════════════════════════════════════
# Texture decoder
# ═══════════════════════════════════════════════════════════════════════════════

def decode_rgb555(c):
    """Saturn RGB555 (ABGR1555): R=bits0-4, G=bits5-9, B=bits10-14, MSB=bit15."""
    return ((c & 0x1F) << 3, ((c >> 5) & 0x1F) << 3, ((c >> 10) & 0x1F) << 3, 255)

def decode_tex(cgb, cmdsrca, cmdcolr, cmdpmod, cmdsize):
    """Decode a VDP1 texture from CGB data.
    
    CMDSRCA × 8 = byte offset into CGB (proven across all asset types).
    CMDCOLR × 8 = LUT byte offset into CGB (for LUT mode).
    
    Returns: (pixel_list, width, height) or (None, w, h) on failure.
    """
    cm = (cmdpmod >> 3) & 7
    tw = (cmdsize & 0x3F00) >> 5
    th = cmdsize & 0xFF
    if tw == 0 or th == 0:
        return None, tw, th
    ta = cmdsrca * 8  # Texture address in CGB
    spd = bool(cmdpmod & 0x40)  # Sprite data = transparent pixel control
    px = []

    if cm == 1:  # 4bpp LUT (16-color palette)
        lut = cmdcolr * 8
        for y in range(th):
            for x in range(0, tw, 2):
                bo = ta + (y * tw + x) // 2
                if bo >= len(cgb):
                    px.extend([(0, 0, 0, 0)] * 2)
                    continue
                bv = cgb[bo]
                for n in range(2):
                    dot = (bv >> 4) & 0xF if n == 0 else bv & 0xF
                    if dot == 0 and not spd:
                        px.append((0, 0, 0, 0))
                    else:
                        po = lut + dot * 2
                        if po + 2 <= len(cgb):
                            c16 = read_u16(cgb, po)
                            px.append(decode_rgb555(c16) if c16 & 0x8000 else (0, 0, 0, 0))
                        else:
                            px.append((255, 0, 255, 255))

    elif cm == 5:  # 16bpp direct RGB555
        for y in range(th):
            for x in range(tw):
                po = ta + (y * tw + x) * 2
                if po + 2 <= len(cgb):
                    c16 = read_u16(cgb, po)
                    px.append((0, 0, 0, 0) if c16 == 0 and not spd else decode_rgb555(c16))
                else:
                    px.append((0, 0, 0, 0))

    elif cm == 0:  # 4bpp bank (greyscale fallback — needs PNB for true palette)
        for y in range(th):
            for x in range(0, tw, 2):
                bo = ta + (y * tw + x) // 2
                if bo >= len(cgb):
                    px.extend([(0, 0, 0, 0)] * 2)
                    continue
                bv = cgb[bo]
                for n in range(2):
                    dot = (bv >> 4) & 0xF if n == 0 else bv & 0xF
                    if dot == 0 and not spd:
                        px.append((0, 0, 0, 0))
                    else:
                        g = dot * 17  # Scale 0-15 to 0-255
                        px.append((g, g, g, 255))

    elif cm == 4:  # 8bpp bank (greyscale fallback — needs PNB for true palette)
        for y in range(th):
            for x in range(tw):
                bo = ta + y * tw + x
                if bo < len(cgb):
                    dot = cgb[bo]
                    px.append((0, 0, 0, 0) if dot == 0 and not spd else (dot, dot, dot, 255))
                else:
                    px.append((0, 0, 0, 0))
    else:
        return None, tw, th

    return (px if len(px) == tw * th else None), tw, th

# ═══════════════════════════════════════════════════════════════════════════════
# MCB auto-classifier
# ═══════════════════════════════════════════════════════════════════════════════

def classify(data, ptrs):
    """Classify all pointer table entries into models, hierarchies, poses, animations, unknown."""
    r = {
        'models': [],       # [(ptr_index, offset)]
        'hierarchies': [],  # [(ptr_index, offset, num_bones)]
        'poses': [],        # [(ptr_index, offset, num_bones, hierarchy_index)]
        'animations': [],   # [(ptr_index, offset, anim_info_dict)]
        'unknown': [],      # [(ptr_index, offset)]
    }
    
    # Pass 1: find hierarchies
    for i in range(len(ptrs)):
        if ptrs[i] == 0:
            continue
        if is_hierarchy(data, ptrs, i):
            r['hierarchies'].append((i, ptrs[i], count_bones(data, ptrs[i])))
    
    # Pass 2: find standalone models (not already claimed by hierarchy)
    hier_indices = {h[0] for h in r['hierarchies']}
    for i in range(len(ptrs)):
        if ptrs[i] == 0 or i in hier_indices:
            continue
        if is_model(data, ptrs, i):
            r['models'].append((i, ptrs[i]))
    
    # Pass 3: find poses and animations for each hierarchy
    for hi, ho, nb in r['hierarchies']:
        pi, po = find_pose(data, ptrs, nb)
        if pi is not None:
            r['poses'].append((pi, po, nb, hi))
            for a in find_anims(data, ptrs, pi, nb):
                r['animations'].append((a['ptr_index'], a['offset'], a))
    
    # Pass 4: tag everything else as unknown
    claimed = set()
    for cat in r.values():
        for e in cat:
            claimed.add(e[0])
    for i in range(len(ptrs)):
        if ptrs[i] != 0 and i not in claimed:
            r['unknown'].append((i, ptrs[i]))
    
    return r

# ═══════════════════════════════════════════════════════════════════════════════
# glTF builder
# ═══════════════════════════════════════════════════════════════════════════════

def build_gltf(name, mcb, cgb, ptrs, cls):
    """Build a glTF 2.0 binary from classified MCB/CGB data.
    
    Strategy:
    1. Try posed hierarchy groups first (dragons, characters, enemies)
    2. If no hierarchy geometry produced, fall back to standalone model extraction
    3. All models placed at origin when extracted standalone (placement needs PRG data)
    """
    
    # ── Phase 1: Collect geometry from posed hierarchies ──
    all_parts = []  # List of (model_offset, world_matrix, bone_index)
    
    for pi, po, nb, hi in cls['poses']:
        # Find the hierarchy offset for this pose
        ho = None
        for h_i, h_o, h_nb in cls['hierarchies']:
            if h_i == hi:
                ho = h_o
                break
        if ho is None:
            continue
        pose = parse_pose(mcb, po, nb)
        parts = walk_hier(mcb, ho, pose)
        # Validate: only include parts where model actually parses
        valid_parts = []
        for moff, xform, bidx in parts:
            m = parse_model(mcb, moff)
            if m and m['quads']:
                valid_parts.append((moff, xform, bidx))
        all_parts.extend(valid_parts)
    
    # ── Phase 2: Standalone models (if hierarchy produced nothing, or always for MP files) ──
    # Collect all model offsets already covered by hierarchy walk
    hier_model_offsets = {p[0] for p in all_parts}
    
    # Always try to include standalone models not covered by hierarchy
    standalone = []
    for i, off in cls['models']:
        if off not in hier_model_offsets:
            m = parse_model(mcb, off)
            if m and m['quads']:
                standalone.append((off, np.eye(4), -1))
    
    # If hierarchy produced nothing at all, also try to parse models from
    # hierarchy pointers that might have been misclassified
    if not all_parts and not standalone:
        # Last resort: try every non-zero pointer as a potential model
        for i in range(len(ptrs)):
            if ptrs[i] == 0:
                continue
            off = ptrs[i]
            if off in hier_model_offsets:
                continue
            m = parse_model(mcb, off)
            if m and m['quads']:
                standalone.append((off, np.eye(4), -1))
    
    all_parts.extend(standalone)
    if not all_parts:
        return None
    
    # ── Phase 3: Decode textures and build face groups ──
    tex_cache = {}    # (cmdsrca, cmdcolr, cmdsize, color_mode) -> tex_index or -1
    tex_pngs = []     # List of PNG bytes
    mat_faces = {}    # tex_index -> {'pos': [], 'uv': [], 'idx': []}
    
    for moff, xform, bidx in all_parts:
        model = parse_model(mcb, moff)
        if not model or not model['quads']:
            continue
        # Transform vertices
        tverts = []
        for vx, vy, vz in model['verts']:
            v = xform @ np.array([vx, vy, vz, 1.0])
            tverts.append((v[0], v[1], v[2]))
        
        for q in model['quads']:
            # Texture key for deduplication
            tk = (q['cmdsrca'], q['cmdcolr'], q['cmdsize'], q['color_mode'])
            if tk not in tex_cache and cgb is not None:
                px, tw, th = decode_tex(cgb, q['cmdsrca'], q['cmdcolr'], q['cmdpmod'], q['cmdsize'])
                if px and tw > 0 and th > 0:
                    img = Image.new('RGBA', (tw, th))
                    img.putdata(px)
                    buf = io.BytesIO()
                    img.save(buf, format='PNG')
                    tex_cache[tk] = len(tex_pngs)
                    tex_pngs.append(buf.getvalue())
                else:
                    tex_cache[tk] = -1
            
            mk = tex_cache.get(tk, -1)
            if mk not in mat_faces:
                mat_faces[mk] = {'pos': [], 'uv': [], 'idx': []}
            
            base = len(mat_faces[mk]['pos']) // 3
            u0, u1 = (1.0, 0.0) if q['flip_h'] else (0.0, 1.0)
            v0, v1 = (1.0, 0.0) if q['flip_v'] else (0.0, 1.0)
            
            for vi, uv in zip(q['idx'], [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]):
                if vi < len(tverts):
                    mat_faces[mk]['pos'].extend(tverts[vi])
                else:
                    mat_faces[mk]['pos'].extend([0, 0, 0])
                mat_faces[mk]['uv'].extend(uv)
            
            # First triangle
            mat_faces[mk]['idx'].extend([base, base + 1, base + 2])
            # Second triangle (if not degenerate quad)
            if q['idx'][2] != q['idx'][3]:
                mat_faces[mk]['idx'].extend([base, base + 2, base + 3])
    
    if not mat_faces:
        return None
    
    # ── Phase 4: Assemble glTF ──
    gltf = GLTF2()
    gltf.scene = 0
    gltf.scenes = [Scene(nodes=[0])]
    gltf.nodes = [Node(name=name, mesh=0)]
    
    binary_data = bytearray()
    prims = []
    buffer_views = []
    accessors = []
    materials = []
    gltf_textures = []
    gltf_images = []
    gltf_samplers = [Sampler(magFilter=9728, minFilter=9728, wrapS=33071, wrapT=33071)]
    
    # Create texture entries
    for ti in range(len(tex_pngs)):
        gltf_images.append(GLTFImage(bufferView=None, mimeType="image/png", name=f"tex_{ti:03d}"))
        gltf_textures.append(Texture(sampler=0, source=ti))
    
    # Create materials and primitives
    mat_index_map = {}
    for mk, fd in mat_faces.items():
        if not fd['idx']:
            continue
        # Create material for this texture
        if mk >= 0 and mk not in mat_index_map:
            m = Material(
                name=f"mat_{mk:03d}",
                pbrMetallicRoughness=pygltflib.PbrMetallicRoughness(
                    baseColorTexture=TextureInfo(index=mk),
                    metallicFactor=0.0, roughnessFactor=0.9
                ),
                alphaMode="MASK", alphaCutoff=0.5, doubleSided=True
            )
            mat_index_map[mk] = len(materials)
            materials.append(m)
        elif mk < 0 and -1 not in mat_index_map:
            m = Material(
                name="untextured",
                pbrMetallicRoughness=pygltflib.PbrMetallicRoughness(
                    baseColorFactor=[0.6, 0.5, 0.4, 1.0],
                    metallicFactor=0.0, roughnessFactor=0.9
                ),
                doubleSided=True
            )
            mat_index_map[-1] = len(materials)
            materials.append(m)
        
        pa = np.array(fd['pos'], dtype=np.float32)
        ua = np.array(fd['uv'], dtype=np.float32)
        ia = np.array(fd['idx'], dtype=np.uint32)
        nv = len(pa) // 3
        
        # Position buffer view + accessor
        po = len(binary_data)
        binary_data.extend(pa.tobytes())
        while len(binary_data) % 4:
            binary_data.append(0)
        pbv = len(buffer_views)
        buffer_views.append(BufferView(buffer=0, byteOffset=po, byteLength=len(pa) * 4, target=ARRAY_BUFFER))
        pr = pa.reshape(-1, 3)
        pac = len(accessors)
        accessors.append(Accessor(
            bufferView=pbv, byteOffset=0, componentType=FLOAT, count=nv,
            type="VEC3", max=pr.max(0).tolist(), min=pr.min(0).tolist()
        ))
        
        # UV buffer view + accessor
        uo = len(binary_data)
        binary_data.extend(ua.tobytes())
        while len(binary_data) % 4:
            binary_data.append(0)
        ubv = len(buffer_views)
        buffer_views.append(BufferView(buffer=0, byteOffset=uo, byteLength=len(ua) * 4, target=ARRAY_BUFFER))
        uac = len(accessors)
        accessors.append(Accessor(
            bufferView=ubv, byteOffset=0, componentType=FLOAT, count=nv, type="VEC2"
        ))
        
        # Index buffer view + accessor
        io_off = len(binary_data)
        binary_data.extend(ia.tobytes())
        while len(binary_data) % 4:
            binary_data.append(0)
        ibv = len(buffer_views)
        buffer_views.append(BufferView(buffer=0, byteOffset=io_off, byteLength=len(ia) * 4, target=ELEMENT_ARRAY_BUFFER))
        iac = len(accessors)
        accessors.append(Accessor(
            bufferView=ibv, byteOffset=0, componentType=UNSIGNED_INT, count=len(ia), type="SCALAR"
        ))
        
        gmi = mat_index_map.get(mk, mat_index_map.get(-1, 0))
        prims.append(Primitive(
            attributes=pygltflib.Attributes(POSITION=pac, TEXCOORD_0=uac),
            indices=iac, material=gmi, mode=TRIANGLES
        ))
    
    if not prims:
        return None
    
    # Embed texture PNGs into the binary buffer
    for ii, pb in enumerate(tex_pngs):
        img_off = len(binary_data)
        binary_data.extend(pb)
        while len(binary_data) % 4:
            binary_data.append(0)
        ibv2 = len(buffer_views)
        buffer_views.append(BufferView(buffer=0, byteOffset=img_off, byteLength=len(pb)))
        gltf_images[ii].bufferView = ibv2
    
    gltf.meshes = [Mesh(name=name, primitives=prims)]
    gltf.materials = materials
    gltf.textures = gltf_textures
    gltf.images = gltf_images
    gltf.samplers = gltf_samplers
    gltf.accessors = accessors
    gltf.bufferViews = buffer_views
    gltf.buffers = [Buffer(byteLength=len(binary_data))]
    
    # ── Phase 5: Extras metadata ──
    anim_info = []
    for _, _, a in cls['animations']:
        anim_info.append({
            'ptr_index': a['ptr_index'], 'flags': a['flags'],
            'num_bones': a['num_bones'], 'num_frames': a['num_frames'],
            'size': a['size']
        })
    hier_info = [{'ptr_index': i, 'num_bones': nb} for i, o, nb in cls['hierarchies']]
    
    gltf.nodes[0].extras = {
        'pds_asset': name,
        'hierarchies': hier_info,
        'animations': anim_info,
        'total_ptrs': len(ptrs),
        'hier_models': len(all_parts) - len(standalone),
        'standalone_models': len(standalone),
        'classified': {
            'models': len(cls['models']),
            'hierarchies': len(cls['hierarchies']),
            'poses': len(cls['poses']),
            'animations': len(cls['animations']),
            'unknown': len(cls['unknown']),
        }
    }
    
    gltf.set_binary_blob(bytes(binary_data))
    return gltf

# ═══════════════════════════════════════════════════════════════════════════════
# Asset extraction
# ═══════════════════════════════════════════════════════════════════════════════

def extract_one(name, mcb, cgb, outdir, include_raw_anims=False):
    """Extract a single MCB/CGB pair to .glb + .json.
    
    Returns stats dict on success, None on failure.
    """
    ptrs = parse_ptrs(mcb)
    if len(ptrs) < 2:
        return None
    cls = classify(mcb, ptrs)
    gltf = build_gltf(name, mcb, cgb, ptrs, cls)
    if gltf is None:
        return None
    
    # Save .glb
    glb_path = os.path.join(outdir, f"{name}.glb")
    gltf.save(glb_path)
    
    # Build JSON sidecar with full metadata
    meta = {
        'name': name,
        'mcb_size': len(mcb),
        'cgb_size': len(cgb) if cgb else 0,
        'ptrs': len(ptrs),
        'hierarchies': [{'idx': i, 'bones': nb} for i, o, nb in cls['hierarchies']],
        'poses': [{'idx': i, 'bones': nb, 'hier': hi} for i, o, nb, hi in cls['poses']],
        'animations': [],
        'models': len(cls['models']),
        'unknown_ptrs': [{'idx': i, 'offset': o} for i, o in cls['unknown']],
    }
    
    for _, off, a in cls['animations']:
        anim_entry = {
            'idx': a['ptr_index'], 'flags': a['flags'],
            'bones': a['num_bones'], 'frames': a['num_frames'],
            'size': a['size'], 'offset': a['offset'],
        }
        if include_raw_anims:
            # Export raw animation binary as base64 for future decoding
            end = a['offset'] + a['size']
            if end <= len(mcb):
                anim_entry['raw_b64'] = base64.b64encode(mcb[a['offset']:end]).decode('ascii')
        meta['animations'].append(anim_entry)
    
    json_path = os.path.join(outdir, f"{name}.json")
    with open(json_path, 'w') as f:
        json.dump(meta, f, indent=2)
    
    fs = os.path.getsize(glb_path)
    return {
        'name': name,
        'size': fs,
        'hier_models': gltf.nodes[0].extras.get('hier_models', 0),
        'standalone_models': gltf.nodes[0].extras.get('standalone_models', 0),
        'hiers': len(cls['hierarchies']),
        'anims': len(cls['animations']),
    }

# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description='PDS MCB/CGB -> glTF 2.0 batch extractor')
    ap.add_argument('disc', help='Raw track image (.bin)')
    ap.add_argument('outdir', help='Output directory for .glb + .json files')
    ap.add_argument('--filter', '-f', help='Name filter pattern (case-insensitive)')
    ap.add_argument('--single', '-s', help='Extract single asset by exact name')
    ap.add_argument('--list', '-l', action='store_true', help='List all assets without extracting')
    ap.add_argument('--verbose', '-v', action='store_true', help='Show detailed progress')
    ap.add_argument('--raw-anims', action='store_true', help='Include raw animation data (base64) in JSON')
    args = ap.parse_args()
    
    print(f"Reading disc: {args.disc}")
    files = parse_iso9660(args.disc)
    
    # Find all MCB/CGB pairs
    mcbs = sorted([n for n in files if n.endswith('.MCB')])
    cgbs = set(n for n in files if n.endswith('.CGB'))
    pairs = []  # (basename, mcb_filename, cgb_filename_or_None)
    mcb_only = []
    for m in mcbs:
        base = m.replace('.MCB', '')
        c = base + '.CGB'
        if c in cgbs:
            pairs.append((base, m, c))
        else:
            mcb_only.append((base, m))
    print(f"Found {len(pairs)} MCB+CGB pairs, {len(mcb_only)} MCB-only")
    
    # Apply filters
    if args.filter:
        p = args.filter.upper()
        pairs = [(b, m, c) for b, m, c in pairs if p in b]
        mcb_only = [(b, m) for b, m in mcb_only if p in b]
    if args.single:
        t = args.single.upper()
        pairs = [(b, m, c) for b, m, c in pairs if b == t]
        mcb_only = [(b, m) for b, m in mcb_only if b == t]
    
    if args.list:
        print(f"\n{'Name':25s}  {'MCB':>10s}  {'CGB':>10s}")
        print("-" * 50)
        for b, m, c in pairs:
            print(f"  {b:25s}  {files[m][1]:>8,d}  {files[c][1]:>8,d}")
        if mcb_only:
            print(f"\n{'MCB Only':25s}  {'MCB':>10s}")
            print("-" * 40)
            for b, m in mcb_only:
                print(f"  {b:25s}  {files[m][1]:>8,d}")
        return
    
    os.makedirs(args.outdir, exist_ok=True)
    ok = fail = total_bytes = 0
    
    # Process all items
    items = [(b, m, c) for b, m, c in pairs] + [(b, m, None) for b, m in mcb_only]
    for b, m, c in items:
        mcb = read_file_from_disc(args.disc, *files[m])
        cgb = read_file_from_disc(args.disc, *files[c]) if c and c in files else None
        try:
            r = extract_one(b, mcb, cgb, args.outdir, include_raw_anims=args.raw_anims)
            if r:
                ok += 1
                total_bytes += r['size']
                hm = r['hier_models']
                sm = r['standalone_models']
                print(f"  OK {b:25s} -> {r['size']:>8,d}B  "
                      f"({hm}h+{sm}s models, {r['hiers']}hier, {r['anims']}anim)")
            else:
                fail += 1
                if args.verbose:
                    print(f"  -- {b:25s} no geometry")
        except Exception as e:
            fail += 1
            print(f"  !! {b:25s} ERROR: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
    
    print(f"\nDone: {ok} extracted, {fail} skipped, "
          f"{total_bytes:,d} bytes ({total_bytes / (1024 * 1024):.1f} MB)")

if __name__ == '__main__':
    main()
