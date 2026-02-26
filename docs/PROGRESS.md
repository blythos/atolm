# Project Progress & Roadmap

## Completed

### Phase 1: Disc Analysis
- [x] ISO9660 filesystem reader for raw Saturn track images
- [x] Complete file inventory of Disc 1 (1,847 files)
- [x] File format identification by extension and content analysis
- [x] 1ST_READ.PRG executable analysis (253KB, SH-2 code, SDK v6.10)

### Phase 2: Format Specification
- [x] MCB format fully documented (pointer table, model structure, hierarchy, pose, animation)
- [x] CGB format fully documented (raw VDP1 pixel data, no header)
- [x] Vertex format: s16 big-endian, 12.4 fixed-point
- [x] Quad format: 20-byte VDP1 command blocks + variable lighting data
- [x] Hierarchy tree: 12-byte nodes (model/child/sibling)
- [x] Static pose: 36 bytes/bone (translation/rotation/scale in 16.16)
- [x] Texture color modes documented (modes 0, 1, 4, 5)
- [x] Saturn RGB555 color format documented
- [x] CMDSRCA×8 = CGB offset verified universally (no per-file VDP1 offset needed)
- [x] CPK/Sega FILM container format documented (`docs/cpk_format_research.md`)
- [x] PRG bytecode subtitle opcodes documented (0x2E, 0x1B, 0x1D, 0x24, 0x07)
- [x] MOVIE.DAT / MOVIE.PRG subtitle mapping structure understood

### Phase 3: Model Extraction
- [x] MCB pointer table auto-classification (models, hierarchies, poses, unknowns)
- [x] Vertex extraction with fixed-point conversion
- [x] Quad parsing with all 4 lighting modes
- [x] Hierarchy tree walker matching engine traversal exactly
- [x] Skeletal transform accumulation (translate → rotateZYX per bone)
- [x] Coordinate space unification (12.4 vertices + 16.16 bones → unified output)
- [x] All 8 dragon forms extracted with correct poses
- [x] Pose data auto-discovery via scale-field heuristic
- [x] Raw binary extraction pipeline (`pds_extract_raw.py`) — outputs raw MCB/CGB + structural JSON

### Phase 4: Texture Extraction
- [x] CGB texture decoder: 4bpp LUT mode (mode 1) — most common
- [x] CGB texture decoder: 16bpp direct RGB mode (mode 5)
- [x] Texture UV mapping with H/V flip support
- [x] Textured OBJ+MTL+PNG export pipeline
- [x] Texture atlas PNG generation for viewer
- [x] Verified across all asset categories (0 failures in testing)

### Phase 5: Cross-Asset Validation
- [x] Dragon (DRAGON0) — 31 bones, 300 verts, 71 textures ✓
- [x] Player character (EDGE) — 6 bones, 81 verts, 33 textures ✓
- [x] Character (AZEL battle) — 6 bones, 76 verts, 31 textures ✓
- [x] NPC (X_A_AZ / Azel) — 17 bones, 265 verts, 87 textures ✓
- [x] NPC (Z_A_EG / Edge in Zoah) — 17 bones, 272 verts, 151 textures ✓
- [x] Enemy (BEMOS) — 7 hierarchies, 948 verts, 143 textures ✓
- [x] Boss (GRIGORIG) — 20 hierarchies, 1642 verts, 299 textures ✓
- [x] Field geometry (FLD_A3_0) — 11 hierarchies, 362 verts, 28 textures ✓

### Phase 6: FMV / Audio Extraction
- [x] CPK Cinepak video extraction to MP4 (`tools/cpk_extract.py`)
- [x] Sega FILM container parsed: FDSC + STAB structure documented
- [x] Audio extraction: 16-bit big-endian PCM → WAV, sample rate 32000 Hz
- [x] Audio/video chunk discrimination via content-aware heuristic
- [x] Subtitle extraction from PRG bytecode (`tools/extract_subtitles.py`)
- [x] Subtitle frame-accurate timing from PRG frame sync opcodes (0x2E)
- [x] MOVIE.DAT fallback subtitle mapping
- [x] SRT generation and MP4 muxing pipeline (`tools/batch_process_FMVs.py`)
- [x] All 47 subtitle groups verified correct (frame-accurate, no misattributions)

### Phase 7: 3D Model Viewer
- [x] Browser-based viewer: `tools/pds_viewer.html` + `viewer_renderer.js` + `viewer_animation.js`
- [x] Three.js WebGL rendering with orbit controls
- [x] Categorised asset browser (Dragons, Characters, NPCs, Fields, Maps, Objects, Overworld)
- [x] Textured quad rendering (LUT, RGB555, greyscale fallback for bank-mode)
- [x] Skeletal pose rendering
- [x] Animation playback — faithful port of Saturn animation state machine
  - [x] Mode 0: Direct per-frame values
  - [x] Mode 1: Accumulated values with variable-length encoding
  - [x] Mode 4: Keyframes every 2 frames with half-step interpolation
  - [x] Mode 5: Keyframes every 4 frames with quarter-step interpolation
- [x] Inspection tools: grid, bounding boxes, bone labels, texture atlas viewer, hex offsets

### Phase 8: Sequential Music
- [x] SEQ file extractor (`tools/seq_extract.py`) — functional
- [x] SEQ to MIDI converter (`tools/seq_to_midi.py`) — functional
- [x] TON to WAV converter (`tools/ton_to_wav.py`) — working; extracts per-instrument WAV samples from BIN tone banks
  - Correct CyberSound TON format parsing (header + voice table + layer blocks)
  - Handles both 8-bit and 16-bit PCM, multi-layer voices, deduplication
  - Out-of-bounds tone_off references (cross-bank samples pre-loaded by companion banks) silently skipped
  - Verified across all 78 standalone BIN files on Disc 1
- [x] SEQ/BIN catalogue (`tools/snd_split.py`) — resolves all 86 SEQ->BIN pairs across all 4 discs; handles 5 shared-bank cases (A3BGM1_1/2->A3BGM, BOSS01_2->A3BOSS, DRG_SE->DRG1SE, TITLE->TITLEBGM); parses AREAMAP.SND
- [x] Sound catalogue builder (`tools/build_sound_catalogue.py`) — parses SNDTEST.PRG for 75 official track names; maps 57 to SEQ files; 29 extra (SFX/battle) tracks exposed for identification; writes output/sound_catalogue.json
- [x] Sound test browser engine (`tools/sound_test_server.py` + `tools/sound_test.html`) — Python HTTP server; browser UI with MIDI playback (html-midi-player + GM soundfont), per-instrument WAV auditioning, search/filter, confidence badges, section grouping; verifies extraction pipeline before SF2/pitch work

## In Progress / Next Steps

### Priority 1: Bank-Mode Textures
- [ ] PNB file parser (VDP2 Color RAM data)
- [ ] Bank-mode palette resolution (modes 0 and 4) — currently greyscale
- [ ] Identify which PNB pairs with which MCB/CGB (may require PRG analysis)

### Priority 2: TON/PCM Audio
- [x] `tools/ton_to_wav.py` — fixed and working
- [x] SND bundle investigation — **RESOLVED**: EPISODE/INTER SND bundles do not exist on disc. AREAMAP.SND is a runtime area-music command stream (276 bytes). All 86 SEQ files are catalogued with correct BIN pairs by `tools/snd_split.py`.
- [ ] PCM audio sample extraction (`tools/pcm_extract.py`) — not yet started
- [ ] Document PCM file format (header vs raw, sample rate, channel count)

### Priority 3: Field Area Rendering

Goal: assemble visitable areas in the 3D viewer with correct model placement.

Knowledge now established (see TECHNICAL_REFERENCE.md PRG section):
- All 30 PRG bytecode opcodes documented
- Field area ID -> PRG filename table known
- FLD_*.PRG binary data section layout known (DataTable3, Grid1, Grid2, DataTable2)
- Field MCB/CGB file lists per area known

Remaining:
- [ ] PRG field data section parser — scan past bytecode, decode DataTable3 grid config,
      Grid1 static geometry entries (model_ref + world XYZ + rotation per cell)
- [ ] Scene assembler — load all MCBs for an area, apply Grid1 world transforms, render in viewer
- [ ] Start with area A3 (FLD_A3.PRG, 4 sub-MCBs) as first test case
- [ ] DataTable2 NPC/object placements (second pass, after static geometry works)

### Priority 4: 2D Assets
- [ ] SCB format parser (VDP2 tilemap/background data)
- [ ] PNB + SCB combined decoder for menu screens, backgrounds
- [x] Font extraction (`tools/fnt_extract.py`) — all 65 FNT files on Disc 1 extracted (16×16 1bpp glyph bitmaps → PNG sprite sheets + JSON)

### Priority 5: glTF Export
- [ ] Export to glTF with embedded skeleton — better than OBJ for animated assets
- [ ] Preserves bone hierarchy, weights, animation tracks

### Priority 6: Multi-Disc Coverage
- [ ] Extend all tools to Discs 2, 3, 4
- [ ] Catalogue any formats unique to later discs

### Phase N: Saturn Generalisation (Long-term)
- [ ] Factor out Saturn-generic components (ISO reader, VDP1 texture decoder, fixed-point utils)
- [ ] Test against other Team Andromeda titles (Panzer Dragoon, Panzer Dragoon Zwei)
- [ ] Document which components are PDS-specific vs Saturn-generic
- [ ] Public tool release

## Asset Counts (Disc 1)

| Type | Count | Status |
|------|-------|--------|
| MCB/CGB pairs | 351 | Extraction pipeline working |
| MCB only (no CGB) | 9 | Collision/pose data, no textures needed |
| CGB only (no MCB) | 19 | 2D screen assets (SCB/PNB system) |
| SCB files | 163 | Not yet parsed |
| PNB files | 162 | Not yet parsed |
| PRG files | 59 | Full opcode table documented (30 opcodes); field binary data layout known; parser not yet built |
| CPK video | 14 | Fully extracted, subtitled MP4s |
| PCM audio | 270 | Not yet extracted |
| SEQ/BIN music | 86 SEQ + 89 BIN | SEQ->MIDI and TON->WAV working; all pairs catalogued (snd_split.py); AREAMAP.SND parsed |
