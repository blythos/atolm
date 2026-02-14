# TASK: Fix PDS Model Viewer — Animation, Textures & Polish

## Context

This is a Panzer Dragoon Saga (Sega Saturn, 1998) 3D model viewer built as part of a reverse engineering / decompilation project. A Python extractor (`pds_extract.py`) reads the game disc and produces JSON files containing 3D models, skeletal hierarchies, textures, and pre-baked animation data. An HTML viewer (`pds_viewer.html`) renders these using Three.js.

The viewer *mostly* works — the dragon model renders with correct shape, textures, and bone hierarchy. But there are specific bugs that need fixing. The viewer code already has a working foundation; the fixes are targeted.

## Current State

The viewer is a single self-contained HTML file with embedded model data. It uses Three.js r128. The extractor produces JSON in a specific format (documented below). Both files are provided.

**What works:**
- Dragon models render with recognizable shape
- Textures (LUT mode 1 and direct RGB mode 5) display correctly
- Bone hierarchy traversal produces correct rest pose
- Animation selector and play/pause UI exists
- Orbit camera controls work

**What's broken (your tasks):**

### Bug 1: Animation — One Model Piece Detaches and Flies Away

When an animation plays, most of the dragon stays still while one piece (appears to be a wing segment) detaches and moves independently. This suggests:

- The animation baking in `pds_extract.py` may have incorrect bone count (`numBones` in the animation header doesn't match the hierarchy bone count)
- OR the bone-to-animation-frame index mapping is misaligned 
- OR the viewer's `walkNode` traversal increments `boneIndex` differently than the extractor's bone ordering

**Diagnosis approach:**
1. Compare `anim.numBones` vs `hierarchy.boneCount` for DRAGON0 — if they differ, the animation applies transforms to the wrong bones
2. Check if the extractor's bone traversal order (when baking) matches the viewer's `walkNode` traversal order (both should be: process node → increment index → recurse children → recurse siblings)
3. The detached piece is hierarchy node 7 (sibling of bone 2), model index 10 (wing base). Check if its bone index in the baked animation corresponds to the correct transform

**Fix:** Ensure the baked animation frame array has one entry per hierarchy bone in the exact traversal order, padding with pose data for bones beyond `numBones`.

### Bug 2: Green/Wrong Textures — Bank Mode Palette Missing  

Many textures appear bright green instead of their correct colors. These are **bank mode** textures (VDP1 color modes 0 and 4) which require external palette data from PNB (Palette Block) files on the disc.

- Color mode 0: 4bpp, palette index = `CMDCOLR | nibble`, palette is in VDP2 Color RAM
- Color mode 4: 8bpp, palette via `CMDCOLR * 2`, also needs VDP2 Color RAM
- Color mode 1 (LUT): Works correctly — palette is inline in the CGB file
- Color mode 5 (RGB555 direct): Works correctly

The extractor currently renders bank-mode textures as greyscale fallback, but some textures are coming out green instead.

**Fix options (in order of effort):**
1. **Immediate fix:** Ensure bank-mode fallback produces clean greyscale (not green). The greyscale code for mode 0 should produce grey pixels: `r=g=b=nibble*17`. Check the mode 4 (8bpp) path too.
2. **Better fix:** Extract palette data from PNB files on the disc. PNB files are paired with SCB files and contain VDP2 Color RAM data. The palette offset for a given texture is `CMDCOLR * 2` bytes into the Color RAM. Each palette entry is RGB555 (same format as LUT palettes). Load the appropriate PNB and use its palette data for bank-mode textures.
3. **Best fix:** Some models share palettes defined in PRG (script) files. This requires analyzing PRG bytecode which is out of scope for now.

### Bug 3: Animation Playback Jerkiness

When animations play, there are periodic "jerks" where the model briefly distorts. This is the keyframe interpolation issue:

- The animation data uses modes 1/2/3 (every frame / every 2 frames / every 4 frames)
- The current linear interpolation between keyframes is close but not exact
- yaz0r's code uses a "half-step" accumulation approach for mode 4 (every 2 frames): on even frames, set absolute values; compute half-delta to next keyframe; on odd frames, add the half-delta
- The extractor's baking uses simple linear interpolation which creates discontinuities at keyframe boundaries

**Fix:** Review the interpolation in `bake_animation()` in the extractor. For mode 2 (interval=2), the interpolation should match yaz0r's approach. The key reference is in `AzelLib/kernel/animation.cpp` in the Azel repository (github.com/yaz0r/Azel).

## Data Format Reference

The JSON produced by the extractor has this structure:

```json
{
  "name": "DRAGON0",
  "pointerTable": [{"index": 0, "offset": 344}, ...],
  "models": {
    "3": {
      "numVertices": 17,
      "vertices": [[0.011, 0.015, -0.002], ...],
      "quads": [{
        "indices": [0, 1, 2, 3],
        "lightingMode": 0,
        "cmdctrl": 0, "cmdpmod": 1228, "cmdcolr": 1532, "cmdsrca": 0, "cmdsize": 528,
        "texWidth": 16, "texHeight": 16, "colorMode": 1,
        "flipH": false, "flipV": false,
        "textureKey": "0_1532_528_1228"
      }, ...]
    },
    "4": { ... }
  },
  "hierarchies": [{
    "ptrIndex": 1,
    "boneCount": 31,
    "nodes": [{
      "offset": 14568, "modelOffset": 428,
      "childOffset": 14580, "siblingOffset": 0,
      "depth": 0, "modelIndex": 3
    }, ...]
  }],
  "poses": [{
    "boneCount": 31,
    "bones": [{
      "translation": [0.0, 0.0, 0.0],
      "rotation": [0.0, 0.0, 0.0],
      "scale": [1.0, 1.0, 1.0]
    }, ...]
  }],
  "animations": [{
    "mode": 4,
    "numBones": 28,
    "numKeyframes": 45,
    "numBakedFrames": 45,
    "frames": [[
      {"translation": [0,0,0], "rotation": [0,0,0], "scale": [1,1,1]},
      ...
    ], ...]
  }],
  "textures": {
    "0_1532_528_1228": {
      "width": 16, "height": 16,
      "colorMode": 1,
      "dataUrl": "data:image/png;base64,..."
    }
  },
  "stats": { ... }
}
```

### Coordinate conventions:
- Vertices: `raw_s16 / 4096.0`
- Bone translations: `raw_s32 / 65536.0`
- Bone rotations: `raw_s32 / 65536.0 * 360.0` (degrees)
- Animation translations: `raw_s16 / 4096.0`
- Animation rotations: raw s16 values = degrees directly
- Z is negated in the viewer for right-hand coordinates: `position.set(x, y, -z)`

### Viewer rotation convention (from working code):
```javascript
boneGroup.position.set(tx, ty, -tz);
boneGroup.rotation.order = 'YXZ';
boneGroup.rotation.set(-rx * toRad, -ry * toRad, -rz * toRad);
```

## Files Provided

1. **`pds_extract.py`** — Python extractor. Reads disc image, produces JSON files.
2. **`pds_viewer.html`** — Self-contained viewer with embedded data for 14 models.
3. **`docs/`** — Project documentation (see PROJECT_SCOPE.md for full format details).

## Validation

- DRAGON0 with Hierarchy 0 selected should show a complete dragon with wings, body, legs, head, tail
- At rest pose (no animation), the model should look correct with no detached parts
- Playing Animation 0 should show a wing-flapping idle animation with all parts staying connected
- Bank-mode textures should render as clean greyscale (not green) until PNB palette support is added
- Switching between DRAGON0-7 should show 8 different dragon forms, all correctly assembled

## Priority Order

1. Fix the detached piece / animation bone mapping (Bug 1) — this is the most visible issue
2. Fix the green texture fallback (Bug 2) — immediate greyscale fix
3. Improve animation smoothness (Bug 3) — refinement

## Reference Resources

- yaz0r's Azel source: `github.com/yaz0r/Azel` — `AzelLib/kernel/animation.cpp` for animation system, `AzelLib/processModel.cpp` for model rendering
- Alex Darby's thread: `twitter-thread.com/t/1242108016629100545` — independent RE work confirming hierarchy format, texture formats, and the "multiply position by 16" scaling
- Sega Saturn VDP1 documentation for texture color modes and quad rendering
