# Project Progress & Roadmap

## Completed

### Phase 1: Disc Analysis
- [x] ISO9660 filesystem reader for raw Saturn track images
- [x] Complete file inventory of Disc 1 (1,847 files)
- [x] File format identification by extension and content analysis
- [x] 1ST_READ.PRG executable analysis (253KB, SH-2 code, SDK v6.10)
- [x] Debug menu discovery (activation via memory patches)

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

### Phase 3: Model Extraction
- [x] MCB pointer table auto-classification (models, hierarchies, poses, unknowns)
- [x] Vertex extraction with fixed-point conversion
- [x] Quad parsing with all 4 lighting modes
- [x] Hierarchy tree walker matching engine traversal exactly
- [x] Skeletal transform accumulation (translate → rotateZYX per bone)
- [x] Coordinate space unification (12.4 vertices + 16.16 bones → unified output)
- [x] All 8 dragon forms extracted with correct poses
- [x] Pose data auto-discovery via scale-field heuristic

### Phase 4: Texture Extraction
- [x] CGB texture decoder: 4bpp LUT mode (mode 1) — most common
- [x] CGB texture decoder: 16bpp direct RGB mode (mode 5)
- [x] Texture UV mapping with H/V flip support
- [x] Textured OBJ+MTL+PNG export pipeline
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

## In Progress / Next Steps

### Phase 6: Remaining Texture Modes
- [ ] PNB file parser (VDP2 Color RAM data)
- [ ] Bank-mode palette resolution (modes 0 and 4) — currently greyscale
- [ ] Identify which PNB pairs with which MCB/CGB (may require PRG analysis)

### Phase 7: Batch Extraction Tool
- [ ] Design tool architecture (ISO reader → browser → selective extraction)
- [ ] Asset catalogue/browser (list disc contents, categorise by naming convention)
- [ ] Batch extraction with progress reporting
- [ ] Output format options (OBJ, possibly glTF for skeletal data)

### Phase 8: Scene Assembly
- [ ] PRG file analysis (SH-2 executable overlays — scene scripts)
- [ ] Model placement data extraction from PRG files
- [ ] Multi-hierarchy assembly for complex models (bosses, vehicles)
- [ ] Field map reconstruction (placing standalone models in world space)

### Phase 9: Animation
- [ ] Animation keyframe format documentation
- [ ] Keyframe decoder (sAnimationData: flags, numBones, numFrames, tracks)
- [ ] Animated model export (glTF with skeletal animation?)

### Phase 10: 2D Assets
- [ ] SCB format parser (VDP2 tilemap/background data)
- [ ] PNB + SCB combined decoder for menu screens, backgrounds
- [ ] Font extraction (.FNT files)

### Phase 11: Audio
- [ ] PCM audio sample extraction
- [ ] SEQ sequenced music analysis
- [ ] CPK Cinepak video extraction

### Phase 12: Saturn Generalisation
- [ ] Factor out Saturn-generic components (ISO reader, VDP1 texture decoder, fixed-point utils)
- [ ] Test against other Team Andromeda titles (Panzer Dragoon, Panzer Dragoon Zwei)
- [ ] Document which components are PDS-specific vs Saturn-generic
- [ ] Public tool release

## Asset Counts (Disc 1)

| Type | Count | Status |
|------|-------|--------|
| MCB/CGB pairs | 351 | Extraction pipeline working |
| MCB only (no CGB) | 9 | Collision/pose data, no textures |
| CGB only (no MCB) | 19 | 2D screen assets (SCB/PNB system) |
| SCB files | 163 | Not yet parsed |
| PNB files | 162 | Not yet parsed |
| PRG files | 59 | Identified as SH-2 overlays, not parsed |
| CPK video | 14 | Not yet extracted |
| PCM audio | 270 | Not yet extracted |
