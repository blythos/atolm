import json
import sys

try:
    with open('output/3d_models/DRAGON1_model.json', 'r') as f:
        data = json.load(f)
except FileNotFoundError:
    print("Error: Model file not found")
    sys.exit(1)

min_v = [float('inf'), float('inf'), float('inf')]
max_v = [float('-inf'), float('-inf'), float('-inf')]
total_mag = 0
count = 0

for model in data['models']:
    for v in model['vertices']:
        # v is [x, y, z] (raw s16)
        mag = (v[0]**2 + v[1]**2 + v[2]**2)**0.5
        total_mag += mag
        count += 1
        
        for i in range(3):
            if v[i] < min_v[i]: min_v[i] = v[i]
            if v[i] > max_v[i]: max_v[i] = v[i]

avg_mag = total_mag / count if count > 0 else 0

print(f"Inspected {len(data['models'])} models, {count} vertices.")
print(f"X Range: {min_v[0]} to {max_v[0]}")
print(f"Y Range: {min_v[1]} to {max_v[1]}")
print(f"Z Range: {min_v[2]} to {max_v[2]}")
print(f"Average Vertex Magnitude (raw): {avg_mag:.2f}")

# And check translation values again for comparison
if 'poses' in data and len(data['poses']) > 0:
    p = data['poses'][0]
    max_t = 0
    for b in p['bones']:
        # Translation is 16.16 FP (so large int)
        tx = b['translation'][0] / 65536.0
        ty = b['translation'][1] / 65536.0
        tz = b['translation'][2] / 65536.0
        mag = (tx**2 + ty**2 + tz**2)**0.5
        if mag > max_t: max_t = mag
    print(f"Max Pose Translation (in 16.16->1.0 units): {max_t:.2f}")
