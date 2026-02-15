#!/usr/bin/env python3
"""Check the scale relationship between vertex positions and bone translations."""
import struct, json, math

data = open('output/raw/DRAGON0.mcb.bin', 'rb').read()
s = json.load(open('output/raw/DRAGON0_structure.json'))

# Find all model offsets 
models = [e for e in s['pointerTable'] if e['type'] == 'model']
print(f"{len(models)} models")

# For each model, find max vertex radius
max_r = 10
for m in models[:5]:
    off = m['offset']
    vert_count = struct.unpack_from('>I', data, off + 4)[0]
    vert_off_rel = struct.unpack_from('>I', data, off + 8)[0]
    vert_off = off + vert_off_rel
    max_local = 0
    for v in range(min(vert_count, 100)):
        voff = vert_off + v * 6
        x = struct.unpack_from('>h', data, voff)[0]
        y = struct.unpack_from('>h', data, voff + 2)[0]
        z = struct.unpack_from('>h', data, voff + 4)[0]
        r = math.sqrt(x*x + y*y + z*z) / 16
        max_local = max(max_local, r)
        max_r = max(max_r, r)
    slot = m['slot']
    print(f"  Model slot {slot}: {vert_count} verts, maxRadius={max_local:.1f}")

print(f"\nMax vertex radius (first 5 models): {max_r:.1f}")
print(f"Camera distance = {max_r * 3:.1f}")
print(f"Wing tip bone translation = {4383/16:.1f}")
print(f"Wing bone(raw=1748) = {1748/16:.1f}")

# Check what max vertex radius would be for ALL models
max_r_all = 10
for m in models:
    off = m['offset']
    vert_count = struct.unpack_from('>I', data, off + 4)[0]
    vert_off_rel = struct.unpack_from('>I', data, off + 8)[0]
    vert_off = off + vert_off_rel
    for v in range(min(vert_count, 200)):
        voff = vert_off + v * 6
        x = struct.unpack_from('>h', data, voff)[0]
        y = struct.unpack_from('>h', data, voff + 2)[0]
        z = struct.unpack_from('>h', data, voff + 4)[0]
        r = math.sqrt(x*x + y*y + z*z) / 16
        max_r_all = max(max_r_all, r)

print(f"\nMax vertex radius (ALL models): {max_r_all:.1f}")
print(f"Camera distance (all) = {max_r_all * 3:.1f}")

# Total bone-chain extent (just wing chain)
pose_off = 15312
print("\n=== Bone chain for wing (bones 8->9->10) ===")
total_tx = 0
total_tz = 0
for bone in [8, 9, 10]:
    boff = pose_off + bone * 36
    tx = struct.unpack_from('>i', data, boff)[0]
    tz = struct.unpack_from('>i', data, boff + 8)[0]
    total_tx += tx
    total_tz += tz
    print(f"  Bone {bone}: tx_raw={tx} tx_world={tx/16:.1f}  (cumulative: {total_tx/16:.1f})")

print(f"\nTotal wing extent from body: {total_tx/16:.1f} world units")
