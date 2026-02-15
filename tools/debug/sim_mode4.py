#!/usr/bin/env python3
"""Simulate mode 4 animation stepping for bone 10 posX to trace the values."""

class TrackState:
    def __init__(self):
        self.currentStep = 0
        self.delay = 0
        self.value = 0

def step_track(state, track_data, max_step):
    if max_step <= 0 or len(track_data) == 0:
        return state.value
    if state.delay > 0:
        state.delay -= 1
        return state.value
    if state.currentStep > 0:
        raw = track_data[state.currentStep] & 0xFFFF
        state.delay = (raw & 0xF) - 1
        val16 = raw & 0xFFF0
        state.value = val16 - 0x10000 if val16 >= 0x8000 else val16
    else:
        state.delay = 0
        state.value = track_data[0] * 16
    state.currentStep += 1
    if state.currentStep >= max_step:
        state.currentStep = 0
    return state.value


def sim_mode4_bone(default_val, track_data, max_step, num_frames):
    """Simulate mode 4 position for one bone channel."""
    ts = TrackState()
    translation = default_val  # _copyPosePositions
    half_t = 0
    
    results = []
    
    # setAnimation calls stepAnimation() for frame 0
    # Mode 4, frame 0, not isSubFrame, frame==0
    translation = step_track(ts, track_data, max_step)
    # Compute half-step
    if num_frames - 1 > 0:
        half_t = int(step_track(ts, track_data, max_step) / 2)
    results.append(("F0(setup)", translation, translation / 16))
    
    # Render loop: frames 1 through numFrames-1
    for frame in range(1, num_frames):
        is_sub = frame & 1
        if is_sub:
            translation += half_t
        else:
            if frame > 0:
                translation += half_t
            if num_frames - 1 > frame:
                half_t = int(step_track(ts, track_data, max_step) / 2)
        results.append((f"F{frame}({'sub' if is_sub else 'key'})", translation, translation / 16))
    
    return results


# DRAGON0 bone 10 posX
default_pose = 4383
track_data = [274, 15, 7]
max_step = 3
num_frames = 45

print("=== First cycle (from setAnimation) ===")
results = sim_mode4_bone(default_pose, track_data, max_step, num_frames)
for r in results[:10]:
    print(f"  {r[0]:12s}: internal={r[1]:8d}  rendered={r[2]:8.1f}")
print(f"  ... (showing first 10 of {len(results)})")
print(f"  {results[-1][0]:12s}: internal={results[-1][1]:8d}  rendered={results[-1][2]:8.1f}")

# Now simulate loop
print("\n=== After loop reset ===")
# The loop code:
# 1. currentFrame = 0
# 2. Reset ALL track states 
# 3. _copyPosePositions (copies default pose)
# 4. stepAnimation() (frame 0)

# So we restart with fresh track states and default pose
results2 = sim_mode4_bone(default_pose, track_data, max_step, num_frames)
for r in results2[:10]:
    print(f"  {r[0]:12s}: internal={r[1]:8d}  rendered={r[2]:8.1f}")
print(f"  ... (showing first 10 of {len(results2)})")
print(f"  {results2[-1][0]:12s}: internal={results2[-1][1]:8d}  rendered={results2[-1][2]:8.1f}")

# Check if all values are ~4384 (consistent with default)
all_internal = [r[1] for r in results]
print(f"\n=== Summary ===")
print(f"Min internal: {min(all_internal)}")
print(f"Max internal: {max(all_internal)}")
print(f"Min rendered: {min(all_internal)/16:.1f}")
print(f"Max rendered: {max(all_internal)/16:.1f}")
print(f"Default pose: {default_pose} -> rendered: {default_pose/16:.1f}")
