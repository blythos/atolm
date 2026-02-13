# Sega Saturn CPK (FILM) Format Analysis

## Overview
The `CPK` files used in *Panzer Dragoon Saga* are a variant of the **Sega FILM** container format, tailored for the Sega Saturn. They contain **Cinepak** compressed video and **Linear PCM** audio.

## Container Structure
The file starts with a standard FILM header, followed by an `FDSC` (File Description) chunk, and then a `STAB` (Sample Table) chunk which indexes the media data.

### FDSC (File Description)
- **Signature**: `FDSC`
- **Metadata**: Contains total file duration, video dimensions, and audio properties.
- **Quirk**: The `sample_rate` field in the FDSC header is often incorrect or garbage (e.g., extremely high values). Do not rely on it.
- **Audio Format**: 16-bit Big-Endian Signed PCM (Default).

### STAB (Sample Table)
The STAB chunk contains a table of 16-byte entries describing each data chunk.
**Entry Layout (Saturn Variant):**
- **0x00-0x03**: `Info1` (Flags/Timestamp?)
- **0x04-0x07**: `Info2` (Type/Grouping)
- **0x08-0x0B**: Offset (Big Endian, relative to Data Base)
- **0x0C-0x0F**: Size (Big Endian)

#### Chunk Identification
The primary challenge is distinguishing Video chunks from Audio chunks, as they share similar flags.

1.  **Video Keyframes**:
    -   Identified by `Info1 == 0xFFFFFFFF`.
    -   Always contain Cinepak Keyframe data.

2.  **Video Interframes vs Audio**:
    -   Both use `Info2 == 0x28` (and varying `Info1` values).
    -   **Video Interframes**: Start with a 4-byte header that matches the Chunk Size (e.g., `00 00 11 28` for a 0x1128 size chunk). The first byte may contain flags (e.g., `01`).
    -   **Audio Chunks**: Start with raw PCM sample data (e.g., `FD 00...`). The values do not resemble a size header.

**Differentiation Algorithm**:
To identify Audio:
1.  Exclude `Info1 == 0xFFFFFFFF`.
2.  Read the first 4 bytes of the chunk (`Header`).
3.  Mask the first byte: `CleanHeader = Header & 0x00FFFFFF`.
4.  If `CleanHeader` equals `ChunkSize`, `ChunkSize-4`, or `ChunkSize-8`, it is a **Video Interframe**.
5.  Otherwise, it is **Audio**.

## Audio Specifics
- **Format**: 16-bit Big-Endian Signed PCM (`>i2`).
- **Channels**: Mono (mostly).
- **Sample Rate**: **32000 Hz**.
    -   The FDSC header does not meaningfully specify this.
    -   Using 44.1kHz results in "chipmunk" speed and desync.
    -   32kHz aligns audio duration with video duration.
-   **Interleaving**: Audio chunks are interleaved with video chunks but provided as raw data blocks (no internal headers).

## Video Specifics
- **Codec**: Cinepak (standard).
- **Resolution**: 320x176 (typically).
- **Quirks**: Video Interframes are stored in separate chunks from the header/metadata chunks in strict interleaving.

## Extraction Logic
For successful extraction:
1.  Parse `STAB`.
2.  Filter Video Keyframes (`FFFFFFFF`).
3.  Filter Video Interframes using the Content-Aware check (Size header match).
4.  Concatenate remaining chunks as Raw PCM.
5.  Convert Big-Endian 16-bit to Little-Endian WAV at **32000 Hz**.
