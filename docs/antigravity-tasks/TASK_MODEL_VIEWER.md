# Task: Browser-Based 3D Model Viewer

## Objective

Create a web-based 3D model viewer (`tools/model_viewer/`) that reads the PDS disc image, lists all 3D model assets, and displays them interactively in the browser with textures, skeletal poses, and orbit camera controls.

## CRITICAL: Do Not Build From Scratch What Already Exists

- **3D rendering**: Use **Three.js** (CDN: `https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js`). Do not write a WebGL renderer from scratch.
- **Orbit controls**: Use Three.js OrbitControls. Do not write camera controls from scratch.
- **Local server**: Use Python's `http.server` module to serve the viewer. Do not install Express, Node, or any web framework.
- **Binary parsing**: All MCB/CGB parsing runs in Python on the server side. The browser receives JSON + PNG textures. Do not attempt to parse Saturn binary formats in JavaScript.
- If you need any npm packages or other tools, **ask the user to install them** rather than building alternatives.

## Architecture

```
Browser (Three.js)  ←→  Python HTTP Server  ←→  Disc Image
     ↑                        ↑
  JSON models              MCB/CGB parser
  PNG textures             (see docs/)
  Orbit camera
```

The Python server:
1. Reads the disc image using the ISO9660 reader (see `docs/QUICK_REFERENCE.md`)
2. Parses MCB/CGB pairs on demand
3. Serves a REST-ish API:
   - `GET /api/assets` → list of all MCB/CGB pairs on disc (name, size, category)
   - `GET /api/model/<name>` → parsed model as JSON (vertices, faces, bone hierarchy, textures)
4. Serves static files (the HTML/JS viewer)

The browser client:
1. Shows a sidebar listing all 351 MCB/CGB pairs, grouped by category (Dragons, Characters, NPCs, Enemies, Fields, etc.)
2. Clicking an asset loads and displays the 3D model
3. Orbit controls for rotation/zoom/pan
4. Textured rendering using the extracted PNG textures

## MCB/CGB Parsing (Server Side)

All binary format details are in `docs/PROJECT_INSTRUCTIONS.md` and `docs/TECHNICAL_REFERENCE.md`. Here is a summary of what you need to implement:

### Reading files from disc
```python
SECTOR_SIZE = 2352; HEADER = 16; DATA = 2048
def read_sector(f, sector_num):
    f.seek(sector_num * SECTOR_SIZE)
    return f.read(SECTOR_SIZE)[HEADER:HEADER + DATA]
```
Parse ISO9660 from PVD at sector 16 to get file locations.

### MCB structure
- Starts with a pointer table: N × u32 big-endian offsets
- Pointer table ends where the first pointed-to data begins
- Sub-resources include models, hierarchy nodes, and pose data

### Classifying pointer table entries
- **Model**: entry at offset where `+0x04` is vertex count (1-5000), `+0x08` is a valid offset
- **Hierarchy**: three u32s (model_offset, child_offset, sibling_offset), all 0 or valid offsets
- **Pose data**: N×36 byte blocks where scale fields (bytes 24-35) ≈ 0x10000

### Vertex format
3 × s16 big-endian, fixed-point 12.4:
```python
x = struct.unpack('>h', data[off:off+2])[0] / 256.0
y = struct.unpack('>h', data[off+2:off+4])[0] / 256.0
z = struct.unpack('>h', data[off+4:off+6])[0] / 256.0
```

### Quad format (20 bytes minimum)
```
+0x00  u16[4]  vertex indices (A, B, C, D) — terminated when all four are 0
+0x08  u16     lightingControl (bits 8-9 = mode: 0=+0 bytes, 1=+8, 2=+48, 3=+24)
+0x0A  u16     CMDCTRL (bits 4-5: H/V texture flip)
+0x0C  u16     CMDPMOD (bits 3-5: color mode)
+0x0E  u16     CMDCOLR (palette address)
+0x10  u16     CMDSRCA (texture source address)
+0x12  u16     CMDSIZE (bits 8-13: width÷8 → shift right 5; bits 0-7: height)
```

Each quad is a face with 4 vertices. If vertex C == vertex D, it's a triangle.

**Lighting mode extra bytes after each quad** — you MUST skip these or parsing goes out of sync:
- Mode 0: +0 bytes
- Mode 1: +8 bytes
- Mode 2: +48 bytes
- Mode 3: +24 bytes

### Texture decoding
Texture byte offset = `CMDSRCA × 8` into the CGB file.
Palette byte offset = `CMDCOLR × 8` into the CGB file (for LUT mode).
Width = `(CMDSIZE & 0x3F00) >> 5`, Height = `CMDSIZE & 0xFF`.
Color mode = `(CMDPMOD >> 3) & 7`:
- **Mode 1** (4bpp LUT): 2 pixels per byte. Palette is 16 × u16 at CMDCOLR×8 in CGB.
- **Mode 5** (16bpp): Direct RGB555. R=bits 0-4, G=bits 5-9, B=bits 10-14.
- **Mode 0** (4bpp bank): Render as greyscale for now (needs PNB palette data we don't have yet).

Decode each unique texture to PNG. Serve as `/api/texture/<name>/<index>.png`.

### Skeletal hierarchy
Walk the hierarchy tree. For each bone, apply: translate → rotateZYX → draw model → recurse children → pop → continue siblings. Rotation order is Z first, then Y, then X. See `docs/TECHNICAL_REFERENCE.md` for the full transform pipeline.

For the JSON API, send pre-transformed vertex positions (apply the bone transforms server-side and output world-space vertices). This is simpler than sending the skeleton to JavaScript.

### UV mapping
VDP1 maps texture corners to quad vertices:
- A → (0,0), B → (1,0), C → (1,1), D → (0,1)
- Apply H-flip and V-flip from CMDCTRL bits 4-5

## Asset Categories (for sidebar grouping)

Group by filename prefix:
- **Dragons**: DRAGON0-7, DRAGONM*, DRAGONC*
- **Characters**: EDGE, AZEL
- **NPCs**: X_A_*, X_E_*, X_F_*, X_G_*, Z_A_*, Z_B_*, Z_E_*, Z_F_*
- **Enemies/Bosses**: Named files (BEMOS, GRIGORIG, BARIOH, RAHAB, etc.)
- **Fields**: FLD_*
- **Maps**: *MP, *MP0-9
- **Other**: Everything else (BATTLE, COMMON3, WORLDMAP, etc.)

## UI Design

Keep it simple and functional:
- Left sidebar: asset list grouped by category, with search/filter
- Main area: Three.js canvas with the 3D model
- Bottom or right panel: asset info (vertex count, face count, bone count, texture count)
- Dark background (like a model viewer should be)
- Loading spinner while models parse

## Running

```bash
# Start the viewer server
python tools/model_viewer/server.py --disc "ISOs/Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin" --port 8080

# Then open http://localhost:8080 in browser
```

## Deliverables

- `tools/model_viewer/server.py` — Python HTTP server with MCB/CGB parser and REST API
- `tools/model_viewer/index.html` — Single-file HTML/JS/CSS viewer using Three.js from CDN
- `tools/model_viewer/README.md` — Brief usage instructions
- Commit message: `[tools] Add browser-based 3D model viewer`

## Validation

- Server starts without errors and serves the viewer page
- Asset list shows all 351 MCB/CGB pairs from Disc 1, grouped by category
- Clicking DRAGON0 shows the Basic Wing dragon with textures and correct pose
- Clicking EDGE shows the player character model with textures
- Clicking a field asset (FLD_A3_0) shows environment geometry
- Orbit controls work (rotate, zoom, pan)
- Models with multiple hierarchies (BEMOS, GRIGORIG) show the first/main hierarchy by default
