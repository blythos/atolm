#!/usr/bin/env python3
"""
pds_extract_raw.py — Panzer Dragoon Saga Raw MCB/CGB Extractor
================================================================

Extracts raw binary MCB/CGB data from a PDS disc image along with
structural analysis metadata. No texture decoding or atlas building
is performed — that is deferred to the viewer/engine at runtime.

Output per MCB/CGB pair:
  - {name}.mcb.bin           Raw MCB bytes (verbatim)
  - {name}.cgb.bin           Raw CGB bytes (verbatim)
  - {name}_structure.json    Pointer table classification + hierarchy

Plus a manifest.json listing all extracted models.

Animation format and data structures derived from analysis of
yaz0r's Azel project (https://github.com/yaz0r/Azel), a partial
reimplementation of PDS. Without their reverse engineering work,
understanding the MCB pointer table layout, animation header format,
and track decompression modes would have been significantly harder.

Usage:
    python pds_extract_raw.py <disc_image.bin> [options]

    --list              List all MCB/CGB pairs on disc
    --extract NAME      Extract a single model by name
    --extract-all       Extract all models
    -o DIR              Output directory (default: output/raw)
    -v                  Verbose output
"""

import argparse
import json
import os
import struct
import sys

# ── ISO9660 Reader ──────────────────────────────────────────────────────────

SECTOR_SIZE = 2352
HEADER_SIZE = 16
DATA_SIZE = 2048


def read_sector(f, sector_num):
    """Read a single 2048-byte sector from a raw disc image."""
    f.seek(sector_num * SECTOR_SIZE + HEADER_SIZE)
    return f.read(DATA_SIZE)


def read_file_from_disc(f, sector, size):
    """Read a file spanning multiple sectors from disc."""
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
    """Parse ISO9660 root directory, return dict of {filename: (sector, size)}."""
    pvd = read_sector(f, 16)
    root_lba = struct.unpack_from('<I', pvd, 156 + 2)[0]
    root_size = struct.unpack_from('<I', pvd, 156 + 10)[0]

    num_sectors = (root_size + DATA_SIZE - 1) // DATA_SIZE
    dir_data = b''
    for i in range(num_sectors):
        dir_data += read_sector(f, root_lba + i)

    files = {}
    pos = 0
    while pos < root_size:
        rec_len = dir_data[pos]
        if rec_len == 0:
            pos = ((pos // DATA_SIZE) + 1) * DATA_SIZE
            if pos >= root_size:
                break
            rec_len = dir_data[pos]
            if rec_len == 0:
                break

        lba = struct.unpack_from('<I', dir_data, pos + 2)[0]
        size = struct.unpack_from('<I', dir_data, pos + 10)[0]
        name_len = dir_data[pos + 32]
        name_raw = dir_data[pos + 33:pos + 33 + name_len]

        if name_len > 1:
            name = name_raw.split(b';')[0].decode('ascii', errors='replace')
            files[name] = (lba, size)

        pos += rec_len

    return files


# ── Binary helpers ──────────────────────────────────────────────────────────

def ru32(d, o): return struct.unpack_from('>I', d, o)[0]
def rs32(d, o): return struct.unpack_from('>i', d, o)[0]
def ru16(d, o): return struct.unpack_from('>H', d, o)[0]
def rs16(d, o): return struct.unpack_from('>h', d, o)[0]


# ── MCB Pointer Table Parser ───────────────────────────────────────────────

def parse_pointer_table(mcb):
    """Parse the MCB pointer table. Returns list of (slot_index, offset) pairs."""
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


# ── Classification Helpers ──────────────────────────────────────────────────

def is_valid_model(mcb, offset):
    """Test if offset points to a valid 3D model header.

    Model header: u32 radius, u32 vertexCount, u32 vertexOffset
    """
    if offset + 12 > len(mcb):
        return False
    vert_count = ru32(mcb, offset + 4)
    vert_offset = ru32(mcb, offset + 8)
    if vert_count < 1 or vert_count > 5000:
        return False
    if vert_offset == 0 or vert_offset >= len(mcb):
        return False
    if vert_offset + vert_count * 6 > len(mcb):
        return False
    return True


def is_valid_hierarchy(mcb, offset):
    """Test if offset points to a valid hierarchy node chain.

    Each node: u32 modelOffset, u32 childOffset, u32 siblingOffset (12 bytes).
    Must form a valid tree with at least 2 nodes.
    """
    if offset + 12 > len(mcb):
        return False

    visited = set()
    count = 0

    def walk(off):
        nonlocal count
        if off == 0 or off >= len(mcb) or off + 12 > len(mcb):
            return True
        if off in visited:
            return False  # cycle
        visited.add(off)

        m = ru32(mcb, off)
        c = ru32(mcb, off + 4)
        s = ru32(mcb, off + 8)

        # All pointers must be zero or valid offsets
        for ptr in [m, c, s]:
            if ptr != 0 and ptr >= len(mcb):
                return False

        count += 1
        if count > 200:
            return False  # sanity limit

        if c != 0:
            if not walk(c):
                return False
        if s != 0:
            if not walk(s):
                return False
        return True

    if not walk(offset):
        return False
    return count >= 2


def count_bones_recursive(mcb, offset):
    """Count bones: 1 + subNode.count + nextNode.count (matches yaz0r's Azel)."""
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


def is_valid_animation(mcb, offset):
    """Test if offset points to valid animation data.

    Animation header (from Azel source sAnimationData constructor):
      u16 flags        — bottom 3 bits = mode (0,1,4,5)
      u16 numBones     — must be 1–100
      u16 numFrames    — must be 1–9999
      u16 pad
      u32 trackHeaderOffset — relative to animation start

    Track header per bone: 9×s16 lengths + 1×u16 pad + 9×u32 offsets = 0x38 bytes
    """
    if offset + 12 > len(mcb):
        return None

    flags = ru16(mcb, offset)
    if flags == 0:
        return None

    mode = flags & 7
    if mode not in (0, 1, 4, 5):
        return None

    num_bones = ru16(mcb, offset + 2)
    num_frames = ru16(mcb, offset + 4)

    if num_bones == 0 or num_bones > 100:
        return None
    if num_frames == 0 or num_frames > 9999:
        return None

    track_header_off = ru32(mcb, offset + 8)
    if track_header_off == 0:
        return None

    abs_track = offset + track_header_off
    if abs_track + num_bones * 0x38 > len(mcb):
        return None

    # Validate at least the first bone's track header structure
    # Track lengths should be small positive values or zero
    valid_tracks = 0
    for i in range(min(9, 3)):  # Check first 3 track lengths
        length = rs16(mcb, abs_track + i * 2)
        if 0 <= length <= 10000:
            valid_tracks += 1

    if valid_tracks < 2:
        return None

    return {
        'flags': flags,
        'mode': mode,
        'numBones': num_bones,
        'numFrames': num_frames,
        'trackHeaderOffset': track_header_off,
        'hasPosition': bool(flags & 8),
        'hasRotation': bool(flags & 0x10),
        'hasScale': bool(flags & 0x20),
    }


def is_valid_pose(mcb, offset, num_bones):
    """Test if offset points to valid static pose data for num_bones.

    Each bone: 9×s32 (translation, rotation, scale) = 36 bytes.
    Scale fields should be approximately 0x10000 (1.0 in 16.16 FP).
    """
    if num_bones == 0 or offset + num_bones * 36 > len(mcb):
        return False

    for b in range(num_bones):
        boff = offset + b * 36
        sx = rs32(mcb, boff + 24)
        sy = rs32(mcb, boff + 28)
        sz = rs32(mcb, boff + 32)
        if not all(0x8000 <= v <= 0x18000 for v in [sx, sy, sz]):
            return False
    return True


# ── Full Pointer Table Classification ───────────────────────────────────────

def classify_pointer_table(mcb, ptrs):
    """Classify every non-zero pointer table entry.

    Order of checks matters:
    1. Hierarchy (most specific structure)
    2. Model
    3. Animation (checked before pose since both are data blocks)
    4. Pose (requires knowing bone count from hierarchies)
    5. Unknown

    Returns list of entry dicts and helper lookups.
    """
    entries = []
    hierarchies = []
    bone_counts = set()

    # Pass 1: find hierarchies and models
    for slot, p in enumerate(ptrs):
        if p == 0:
            entries.append({'slot': slot, 'offset': p, 'type': 'zero'})
            continue

        if is_valid_hierarchy(mcb, p):
            bc = count_bones_recursive(mcb, p)
            hierarchies.append({'slot': slot, 'offset': p, 'boneCount': bc})
            bone_counts.add(bc)
            entries.append({'slot': slot, 'offset': p, 'type': 'hierarchy', 'boneCount': bc})
        elif is_valid_model(mcb, p):
            entries.append({'slot': slot, 'offset': p, 'type': 'model'})
        else:
            entries.append({'slot': slot, 'offset': p, 'type': 'pending'})

    # Pass 2: check pending entries for animation and pose
    for entry in entries:
        if entry['type'] != 'pending':
            continue

        p = entry['offset']

        # Check animation
        anim_info = is_valid_animation(mcb, p)
        if anim_info:
            entry['type'] = 'animation'
            entry.update(anim_info)
            continue

        # Check pose (try each known bone count)
        found_pose = False
        for bc in sorted(bone_counts, reverse=True):
            if is_valid_pose(mcb, p, bc):
                entry['type'] = 'pose'
                entry['boneCount'] = bc
                found_pose = True
                break

        if not found_pose:
            entry['type'] = 'unknown'

    return entries, hierarchies


# ── Hierarchy Tree Serialization ────────────────────────────────────────────

def serialize_hierarchy(mcb, offset):
    """Walk hierarchy tree and serialize to a list of node dicts."""
    nodes = []

    def walk(off, depth=0):
        if off == 0 or off >= len(mcb) or off + 12 > len(mcb):
            return
        model_off = ru32(mcb, off)
        child_off = ru32(mcb, off + 4)
        sibling_off = ru32(mcb, off + 8)

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


# ── Model Categorization ───────────────────────────────────────────────────

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
    if 'MP' in n and (n.endswith('MP') or any(n.endswith(f'MP{s}') for s in '0123456789DN')):
        return 'Maps'
    if n.endswith('OBJ') or 'OBJ' in n:
        return 'Objects'
    if n.endswith('_OW'):
        return 'Overworld'
    return 'Other'


# ── Main Extraction ─────────────────────────────────────────────────────────

def extract_raw(name, mcb, cgb, output_dir, verbose=False):
    """Extract a single MCB/CGB pair as raw binary + structural JSON."""
    os.makedirs(output_dir, exist_ok=True)

    # Write raw binary files
    mcb_path = os.path.join(output_dir, f'{name}.mcb.bin')
    with open(mcb_path, 'wb') as f:
        f.write(mcb)

    if cgb:
        cgb_path = os.path.join(output_dir, f'{name}.cgb.bin')
        with open(cgb_path, 'wb') as f:
            f.write(cgb)

    # Parse and classify pointer table
    ptrs = parse_pointer_table(mcb)
    entries, hierarchies = classify_pointer_table(mcb, ptrs)

    # Serialize hierarchies
    hier_details = []
    for h in hierarchies:
        nodes = serialize_hierarchy(mcb, h['offset'])
        hier_details.append({
            'slot': h['slot'],
            'offset': h['offset'],
            'boneCount': h['boneCount'],
            'nodes': nodes,
        })

    # Collect slot lists by type
    type_counts = {}
    for e in entries:
        t = e['type']
        type_counts[t] = type_counts.get(t, 0) + 1

    animation_slots = [e['slot'] for e in entries if e['type'] == 'animation']
    model_slots = [e['slot'] for e in entries if e['type'] == 'model']
    pose_slots = [e['slot'] for e in entries if e['type'] == 'pose']

    # Build structure JSON — only non-zero entries in the pointer table
    structure = {
        'name': name,
        'mcbSize': len(mcb),
        'cgbSize': len(cgb) if cgb else 0,
        'pointerTableSlots': len(ptrs),
        'pointerTable': [e for e in entries if e['type'] != 'zero'],
        'hierarchies': hier_details,
        'modelSlots': model_slots,
        'animationSlots': animation_slots,
        'poseSlots': pose_slots,
        'typeCounts': type_counts,
    }

    structure_path = os.path.join(output_dir, f'{name}_structure.json')
    with open(structure_path, 'w') as f:
        json.dump(structure, f, indent=2)

    if verbose:
        anim_count = len(animation_slots)
        model_count = len(model_slots)
        hier_count = len(hierarchies)
        pose_count = len(pose_slots)
        print(f"  {name}: {model_count}m {hier_count}h {pose_count}p {anim_count}a "
              f"({len(ptrs)} slots, MCB={len(mcb)} CGB={len(cgb) if cgb else 0})")

    return {
        'models': len(model_slots),
        'hierarchies': len(hierarchies),
        'poses': len(pose_slots),
        'animations': len(animation_slots),
        'pointerTableSlots': len(ptrs),
    }


def main():
    parser = argparse.ArgumentParser(
        description='Panzer Dragoon Saga — Raw MCB/CGB Extractor\n\n'
                    'Dumps raw binary MCB/CGB data with structural analysis.\n'
                    'Animation format derived from yaz0r\'s Azel project\n'
                    '(https://github.com/yaz0r/Azel).',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('disc', help='Path to disc track image (.bin)')
    parser.add_argument('--list', action='store_true', help='List all MCB/CGB pairs')
    parser.add_argument('--extract', metavar='NAME',
                        help='Extract a single model by name (without extension)')
    parser.add_argument('--extract-all', action='store_true', help='Extract all models')
    parser.add_argument('-o', '--output', default='output/raw',
                        help='Output directory (default: output/raw)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    args = parser.parse_args()

    with open(args.disc, 'rb') as f:
        files = parse_iso_directory(f)

        # Find MCB/CGB pairs
        mcb_files = sorted([n for n in files if n.upper().endswith('.MCB')])
        cgb_lookup = {n.upper(): n for n in files if n.upper().endswith('.CGB')}

        pairs = []
        for mcb_name in mcb_files:
            base = mcb_name.rsplit('.', 1)[0]
            cgb_key = base + '.CGB'
            cgb_name = cgb_lookup.get(cgb_key.upper())
            pairs.append((base, mcb_name, cgb_name, cgb_name is not None))

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
                    print(f"  {base:25s}  MCB: {ms:>8d}  {cgb_info}")

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

            print(f"Extracting {base} (raw)...")
            result = extract_raw(base, mcb_data, cgb_data, args.output, args.verbose)
            print(f"Done: {result}")

        elif args.extract_all:
            print(f"Extracting {len(pairs)} models (raw) to {args.output}/")

            manifest = {
                'version': 1,
                'generator': 'pds_extract_raw.py',
                'credits': 'Animation format derived from yaz0r\'s Azel project '
                           '(https://github.com/yaz0r/Azel)',
                'models': [],
                'categories': {},
            }

            for i, (base, mcb_name, cgb_name, has_cgb) in enumerate(pairs):
                mcb_sector, mcb_size = files[mcb_name]
                mcb_data = read_file_from_disc(f, mcb_sector, mcb_size)

                cgb_data = b''
                if has_cgb and cgb_name in files:
                    cgb_sector, cgb_size = files[cgb_name]
                    cgb_data = read_file_from_disc(f, cgb_sector, cgb_size)

                try:
                    result = extract_raw(base, mcb_data, cgb_data,
                                         args.output, args.verbose)
                    cat = categorize_name(base)
                    entry = {
                        'name': base,
                        'category': cat,
                        'hasCGB': has_cgb,
                        'mcbSize': mcb_size,
                        'cgbSize': files[cgb_name][1] if cgb_name and cgb_name in files else 0,
                        **result,
                    }
                    manifest['models'].append(entry)
                    if cat not in manifest['categories']:
                        manifest['categories'][cat] = []
                    manifest['categories'][cat].append(base)

                    print(f"  [{i+1}/{len(pairs)}] {base}: "
                          f"{result['models']}m {result['hierarchies']}h "
                          f"{result['animations']}a")
                except Exception as e:
                    print(f"  [{i+1}/{len(pairs)}] {base}: ERROR — {e}")

            manifest_path = os.path.join(args.output, 'manifest.json')
            with open(manifest_path, 'w') as mf:
                json.dump(manifest, mf, indent=2)

            total_anims = sum(m.get('animations', 0) for m in manifest['models'])
            total_models = sum(m.get('models', 0) for m in manifest['models'])
            print(f"\nDone. {len(manifest['models'])} assets, "
                  f"{total_models} models, {total_anims} animations.")
            print(f"Manifest: {manifest_path}")

        else:
            parser.print_help()


if __name__ == '__main__':
    main()
