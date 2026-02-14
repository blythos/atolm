"""
Panzer Dragoon Saga — FMV Subtitle Extractor

Extracts subtitle text and frame-accurate timing from PRG overlay files
using the game's bytecode script interpreter format, as documented in
yaz0r's Azel project (AzelLib/town/townScript.cpp).

The game's script system uses these key opcodes for FMV subtitles:
  - opcode 46 (0x2E): cutsceneFrameSync — wait until FMV reaches frame N
  - opcode 27 (0x1B): drawString — display subtitle text
  - opcode 29 (0x1D): clearString — clear subtitle text
  - opcode 36 (0x24): displayTimedString — show text for N frames
  - opcode  7 (0x07): callNative — used to call createEPKPlayer(filename)

Subtitle timing comes from the frame sync opcodes; the text comes from
string pointers resolved against the PRG's load base address.

Fallback: Also reads MOVIE.DAT (a flat subtitle table) for any CPKs
not covered by PRG parsing.

Usage:
    python extract_subtitles.py --iso path/to/disc1.bin --output output/subtitles
"""

import os
import sys
import struct
import argparse
import re
from collections import defaultdict, Counter

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from tools.common.iso9660 import ISO9660Reader
except ImportError:
    sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'common'))
    from iso9660 import ISO9660Reader


# ---------------------------------------------------------------------------
# Binary helpers
# ---------------------------------------------------------------------------

def read_u8(data, offset):
    return data[offset]

def read_s8(data, offset):
    return struct.unpack('>b', data[offset:offset+1])[0]

def read_u16_be(data, offset):
    return struct.unpack('>H', data[offset:offset+2])[0]

def read_s16_be(data, offset):
    return struct.unpack('>h', data[offset:offset+2])[0]

def read_u32_be(data, offset):
    return struct.unpack('>I', data[offset:offset+4])[0]

def align2(offset):
    """Advance to next 2-byte boundary."""
    return (offset + 1) & ~1

def align4(offset):
    """Advance to next 4-byte boundary."""
    return (offset + 3) & ~3

def read_cstring(data, offset):
    """Read null-terminated ASCII string."""
    if offset < 0 or offset >= len(data):
        return ''
    end = offset
    while end < len(data) and data[end] != 0:
        end += 1
    try:
        return data[offset:end].decode('ascii', errors='replace')
    except Exception:
        return ''


# ---------------------------------------------------------------------------
# SRT timestamp formatting
# ---------------------------------------------------------------------------

def frame_to_srt_ts(frame, fps=15.0):
    """Convert a frame number to SRT timestamp string."""
    seconds = max(0, frame) / fps
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    ms = (s - int(s)) * 1000
    return f"{int(h):02}:{int(m):02}:{int(s):02},{int(ms):03}"


# ---------------------------------------------------------------------------
# PRG base address detection
# ---------------------------------------------------------------------------

def detect_prg_base(data):
    """Detect the Saturn load base address for a PRG overlay.

    PRG overlays are loaded to specific addresses in Work RAM.
    Internal pointers reference data within the file using absolute
    Saturn addresses. We scan for u32 values that look like pointers
    into the file and find the most common base alignment.

    Common bases: 0x06010000, 0x06050000, 0x06040000, etc.
    """
    candidates = Counter()
    file_size = len(data)

    for i in range(0, min(len(data) - 4, 0x2000), 4):
        val = read_u32_be(data, i)
        # Saturn Work RAM High range
        if 0x06000000 <= val <= 0x060FFFFF:
            potential_offset = val - (val & 0xFFFF0000)
            if potential_offset < file_size:
                base = val & 0xFFFF0000
                candidates[base] += 1
        # Work RAM Low range
        elif 0x00200000 <= val <= 0x002FFFFF:
            base = val & 0xFFFF0000
            potential_offset = val - base
            if potential_offset < file_size and base % 0x10000 == 0:
                candidates[base] += 1

    if candidates:
        return candidates.most_common(1)[0][0]
    return None


# ---------------------------------------------------------------------------
# PRG string and CPK reference extraction
# ---------------------------------------------------------------------------

def find_cpk_references(data):
    """Find CPK filename strings in PRG data."""
    cpk_names = []
    for match in re.finditer(rb'[\w_-]+\.[Cc][Pp][Kk]\x00', data):
        name = match.group()[:-1].decode('ascii').upper()
        offset = match.start()
        cpk_names.append((offset, name))
    return cpk_names


# ---------------------------------------------------------------------------
# Bytecode script interpreter — subtitle-relevant opcode parsing
#
# All opcodes and their data consumption rules come directly from
# yaz0r's townScript.cpp runScript() function (lines 1661-2043).
# ---------------------------------------------------------------------------

# Opcodes (decimal values used in the switch statement)
OP_END              = 1   # 0x01
OP_WAIT             = 2   # 0x02
OP_JUMP             = 3   # 0x03
OP_IF               = 5   # 0x05
OP_CALL_SCRIPT      = 6   # 0x06
OP_CALL_NATIVE      = 7   # 0x07
OP_EQUAL            = 8   # 0x08
OP_NOT_EQUAL        = 9   # 0x09
OP_GREATER          = 10  # 0x0A
OP_GREATER_EQ       = 11  # 0x0B
OP_LESS             = 12  # 0x0C
OP_LESS_EQ          = 13  # 0x0D
OP_SET_BIT          = 15  # 0x0F
OP_GET_BIT          = 17  # 0x11
OP_READ_PACKED      = 18  # 0x12
OP_ADD_PACKED       = 20  # 0x14
OP_SWITCH           = 21  # 0x15
OP_SET_RESULT       = 24  # 0x18
OP_ADD_CINEMA_BARS  = 25  # 0x19
OP_RM_CINEMA_BARS   = 26  # 0x1A
OP_DRAW_STRING      = 27  # 0x1B
OP_CLEAR_STRING     = 29  # 0x1D
OP_WAIT_NATIVE      = 31  # 0x1F
OP_WAIT_FADE        = 32  # 0x20
OP_PLAY_SFX         = 33  # 0x21
OP_PLAY_PCM         = 34  # 0x22
OP_DISPLAY_TIMED    = 36  # 0x24
OP_MULTI_CHOICE     = 39  # 0x27
OP_GET_INVENTORY    = 41  # 0x29
OP_ADD_INVENTORY    = 43  # 0x2B
OP_CUTSCENE_SYNC    = 46  # 0x2E
OP_RECEIVE_ITEM     = 48  # 0x30

# Set of all known opcodes for validation
KNOWN_OPCODES = {
    OP_END, OP_WAIT, OP_JUMP, OP_IF, OP_CALL_SCRIPT, OP_CALL_NATIVE,
    OP_EQUAL, OP_NOT_EQUAL, OP_GREATER, OP_GREATER_EQ, OP_LESS, OP_LESS_EQ,
    OP_SET_BIT, OP_GET_BIT, OP_READ_PACKED, OP_ADD_PACKED, OP_SWITCH,
    OP_SET_RESULT, OP_ADD_CINEMA_BARS, OP_RM_CINEMA_BARS,
    OP_DRAW_STRING, OP_CLEAR_STRING, OP_WAIT_NATIVE, OP_WAIT_FADE,
    OP_PLAY_SFX, OP_PLAY_PCM, OP_DISPLAY_TIMED, OP_MULTI_CHOICE,
    OP_GET_INVENTORY, OP_ADD_INVENTORY, OP_CUTSCENE_SYNC, OP_RECEIVE_ITEM,
}


def resolve_string_ptr(data, ptr_val, base_addr):
    """Resolve a Saturn absolute address to a string in the PRG file.

    The drawString opcode (case 27 in townScript.cpp) does:
        r14 = getAlignOn4(r14);
        VDP2DrawString(readSaturnString(readSaturnEA(r14)).c_str());
        r14 += 4;

    readSaturnEA reads a 32-bit pointer from memory at r14, then
    readSaturnString reads the null-terminated string at that pointer.
    So it's a double indirection: r14 -> ptr -> string.

    However, in the PRG file's data section, the value at the script
    position may be either:
      (a) A pointer to a pointer to the string (double indirection)
      (b) A direct pointer to the string

    We try both and return whichever yields valid ASCII text.
    """
    bases_to_try = []
    if base_addr:
        bases_to_try.append(base_addr)
    # Also try common bases
    for b in [0x06050000, 0x06040000, 0x06010000, 0x06060000,
              0x00250000, 0x00200000]:
        if b not in bases_to_try:
            bases_to_try.append(b)

    for base in bases_to_try:
        file_off = ptr_val - base
        if not (0 <= file_off < len(data)):
            continue

        # Try double indirection first (the correct interpretation per Azel)
        if file_off + 4 <= len(data):
            inner_ptr = read_u32_be(data, file_off)
            inner_off = inner_ptr - base
            if 0 <= inner_off < len(data):
                text = read_cstring(data, inner_off)
                if text and len(text) >= 2 and text.isprintable():
                    return text

        # Try direct: ptr_val points directly to the string
        text = read_cstring(data, file_off)
        if text and len(text) >= 2 and text.isprintable():
            return text

    return ''


def try_parse_script_region(data, base_addr, region_start, region_end):
    """Attempt to parse a bytecode script region and extract subtitle events.

    Returns a list of events on success, or None if parsing fails
    (too many unrecognised opcodes = not a valid script region).
    """
    events = []
    pos = region_start
    max_pos = min(region_end, len(data))
    error_count = 0
    max_errors = 3

    while pos < max_pos:
        opcode = data[pos]
        pos += 1

        if opcode == 0x00:
            # Padding/NOP
            continue

        if opcode == OP_END:
            break

        elif opcode == OP_WAIT:
            pos = align2(pos)
            if pos + 2 > max_pos: break
            pos += 2  # u16 delay

        elif opcode == OP_JUMP:
            pos = align4(pos)
            if pos + 4 > max_pos: break
            pos += 4  # u32 target

        elif opcode == OP_IF:
            pos = align4(pos)
            if pos + 4 > max_pos: break
            pos += 4  # u32 target

        elif opcode == OP_CALL_SCRIPT:
            pos = align4(pos)
            if pos + 4 > max_pos: break
            pos += 4  # u32 target

        elif opcode == OP_CALL_NATIVE:
            if pos >= max_pos: break
            num_args = read_u8(data, pos)
            pos += 1
            pos = align4(pos)
            if pos + 4 + num_args * 4 > max_pos: break
            func_addr = read_u32_be(data, pos)
            pos += 4
            args = []
            for _ in range(num_args):
                args.append(read_u32_be(data, pos))
                pos += 4
            events.append({'type': 'call_native', 'func': func_addr,
                           'args': args})

        elif opcode in (OP_EQUAL, OP_NOT_EQUAL, OP_GREATER, OP_GREATER_EQ,
                        OP_LESS, OP_LESS_EQ):
            pos = align2(pos)
            if pos + 2 > max_pos: break
            pos += 2  # s16 value

        elif opcode in (OP_SET_BIT, OP_GET_BIT):
            pos = align2(pos)
            if pos + 2 > max_pos: break
            pos += 2  # s16 bit index

        elif opcode == OP_READ_PACKED:
            pos += 1  # s8 bit count
            pos = align2(pos)
            if pos + 2 > max_pos: break
            pos += 2  # s16 var index

        elif opcode == OP_ADD_PACKED:
            pos += 1  # s8 bit count
            pos = align2(pos)
            if pos + 4 > max_pos: break
            pos += 4  # s16 var index + s16 addend

        elif opcode == OP_SWITCH:
            if pos >= max_pos: break
            arg = read_s8(data, pos)
            pos += 1
            pos = align4(pos)
            if pos >= max_pos: break
            count = read_u8(data, pos)
            # Skip the jump table — use max(arg, count) entries
            skip_count = max(arg, count)
            if skip_count <= 0 or skip_count > 64:
                error_count += 1
                if error_count > max_errors: return None
                continue
            if pos + skip_count * 4 > max_pos: break
            pos += skip_count * 4

        elif opcode == OP_SET_RESULT:
            pass  # no data bytes

        elif opcode == OP_ADD_CINEMA_BARS:
            pass  # no data bytes

        elif opcode == OP_RM_CINEMA_BARS:
            pass  # no data bytes

        elif opcode == OP_DRAW_STRING:
            pos = align4(pos)
            if pos + 4 > max_pos: break
            ptr_val = read_u32_be(data, pos)
            pos += 4
            text = resolve_string_ptr(data, ptr_val, base_addr)
            if text:
                events.append({'type': 'draw_string', 'text': text,
                               'ptr': ptr_val})

        elif opcode == OP_CLEAR_STRING:
            events.append({'type': 'clear_string'})

        elif opcode == OP_WAIT_NATIVE:
            # Same format as callNative: u8 numArgs, align4, funcAddr, args
            if pos >= max_pos: break
            num_args = read_u8(data, pos)
            pos += 1
            pos = align4(pos)
            if pos + 4 + num_args * 4 > max_pos: break
            pos += 4 + num_args * 4

        elif opcode == OP_WAIT_FADE:
            pass  # no data bytes

        elif opcode == OP_PLAY_SFX:
            pos += 1  # s8 sfx_id

        elif opcode == OP_PLAY_PCM:
            pos += 1  # s8 pcm_id

        elif opcode == OP_DISPLAY_TIMED:
            # From townScript.cpp case 36:
            #   r14 = getAlignOn2(r14);
            #   s16 duration = readSaturnS16(r14); r14 += 2;
            #   r14 = getAlignOn4(r14);
            #   sSaturnPtr stringPtr = readSaturnEA(r14); r14 += 4;
            pos = align2(pos)
            if pos + 2 > max_pos: break
            duration = read_s16_be(data, pos)
            pos += 2
            pos = align4(pos)
            if pos + 4 > max_pos: break
            ptr_val = read_u32_be(data, pos)
            pos += 4
            text = resolve_string_ptr(data, ptr_val, base_addr)
            if text:
                events.append({'type': 'timed_string', 'text': text,
                               'duration': duration, 'ptr': ptr_val})

        elif opcode == OP_MULTI_CHOICE:
            # First invocation path (no active task): reads s8 count,
            # then if count > 0: align4 + count*4 bytes of choice pointers
            if pos >= max_pos: break
            arg = read_s8(data, pos)
            pos += 1
            if arg > 0:
                pos = align4(pos)
                if pos + arg * 4 > max_pos: break
                pos += arg * 4

        elif opcode == OP_GET_INVENTORY:
            pos = align2(pos)
            if pos + 2 > max_pos: break
            pos += 2  # s16 item index

        elif opcode == OP_ADD_INVENTORY:
            pos += 1  # s8 count
            pos = align2(pos)
            if pos + 2 > max_pos: break
            pos += 2  # s16 item index

        elif opcode == OP_CUTSCENE_SYNC:
            pos = align2(pos)
            if pos + 2 > max_pos: break
            frame = read_s16_be(data, pos)
            pos += 2
            events.append({'type': 'frame_sync', 'frame': frame})

        elif opcode == OP_RECEIVE_ITEM:
            pos = align2(pos)
            if pos + 6 > max_pos: break
            pos += 6  # s16 + s16 + s16

        else:
            error_count += 1
            if error_count > max_errors:
                return None
            continue

    return events if events else None


# ---------------------------------------------------------------------------
# Script region discovery
# ---------------------------------------------------------------------------

def find_script_regions(data):
    """Scan PRG binary for likely script bytecode regions.

    Looks for concentrations of opcode 0x2E (cutsceneFrameSync) with
    valid-looking frame numbers, which is the most distinctive marker
    of FMV subtitle script sections.
    """
    regions = []

    # Find all positions that look like frame sync opcodes
    sync_positions = []
    for i in range(len(data) - 3):
        if data[i] == 0x2E:
            a = align2(i + 1)
            if a + 2 <= len(data):
                frame = read_s16_be(data, a)
                if 0 <= frame <= 15000:
                    sync_positions.append(i)

    if not sync_positions:
        return regions

    # Cluster nearby sync positions
    clusters = []
    current_cluster = [sync_positions[0]]
    for pos in sync_positions[1:]:
        if pos - current_cluster[-1] < 300:
            current_cluster.append(pos)
        else:
            if len(current_cluster) >= 2:
                clusters.append(current_cluster)
            current_cluster = [pos]
    if len(current_cluster) >= 2:
        clusters.append(current_cluster)

    for cluster in clusters:
        # Expand region backwards to find script start
        start = cluster[0]
        for scan_back in range(cluster[0], max(0, cluster[0] - 4096), -1):
            if data[scan_back] in (0x07, 0x19):  # callNative or addCinemaBars
                start = scan_back
                break
        else:
            start = max(0, cluster[0] - 256)

        # Expand region forward to find script end
        end = cluster[-1] + 64
        for scan_fwd in range(cluster[-1], min(len(data), cluster[-1] + 4096)):
            if data[scan_fwd] == 0x01:  # end opcode
                end = scan_fwd + 1
                break

        regions.append((start, end))

    return regions


# ---------------------------------------------------------------------------
# Build subtitle timeline from parsed events
# ---------------------------------------------------------------------------

def events_to_subtitles(events):
    """Convert a list of script events into a subtitle timeline.

    Returns list of {'start_frame': N, 'end_frame': N, 'text': "..."}.
    """
    subtitles = []
    current_frame = 0
    current_text = None
    current_start = 0

    for evt in events:
        if evt['type'] == 'frame_sync':
            current_frame = evt['frame']

        elif evt['type'] == 'draw_string':
            # If there's already a subtitle showing, close it at this frame
            if current_text is not None:
                subtitles.append({
                    'start_frame': current_start,
                    'end_frame': current_frame,
                    'text': current_text
                })
            current_text = evt['text']
            current_start = current_frame

        elif evt['type'] == 'clear_string':
            if current_text is not None:
                subtitles.append({
                    'start_frame': current_start,
                    'end_frame': current_frame,
                    'text': current_text
                })
                current_text = None

        elif evt['type'] == 'timed_string':
            # Close any existing subtitle first
            if current_text is not None:
                subtitles.append({
                    'start_frame': current_start,
                    'end_frame': current_frame,
                    'text': current_text
                })
            # Timed strings are self-clearing
            subtitles.append({
                'start_frame': current_frame,
                'end_frame': current_frame + evt['duration'],
                'text': evt['text']
            })
            current_text = None

    # Close any remaining open subtitle with a default duration
    if current_text is not None:
        subtitles.append({
            'start_frame': current_start,
            'end_frame': current_start + 90,  # 6s at 15fps
            'text': current_text
        })

    # Filter: must have text and positive duration
    subtitles = [s for s in subtitles
                 if s['text'] and s['end_frame'] > s['start_frame']]

    return subtitles


# ---------------------------------------------------------------------------
# PRG-based extraction (primary approach)
# ---------------------------------------------------------------------------

def extract_from_prg(prg_data, prg_name):
    """Extract subtitle data from a single PRG file.

    Returns dict: {cpk_name: [subtitle_entries]}.
    """
    results = {}

    base_addr = detect_prg_base(prg_data)
    if base_addr:
        print(f"  {prg_name}: base=0x{base_addr:08X}")
    else:
        print(f"  {prg_name}: could not detect base address")

    cpk_refs = find_cpk_references(prg_data)
    if not cpk_refs:
        return results

    print(f"  {prg_name}: CPK refs: {[name for _, name in cpk_refs]}")

    regions = find_script_regions(prg_data)
    if not regions:
        print(f"  {prg_name}: no script regions found")
        return results

    print(f"  {prg_name}: {len(regions)} candidate script region(s)")

    # Parse each region and collect all events
    all_events = []
    for rstart, rend in regions:
        events = try_parse_script_region(prg_data, base_addr, rstart, rend)
        if events:
            all_events.extend(events)

    if not all_events:
        print(f"  {prg_name}: no events parsed from script regions")
        return results

    sync_count = sum(1 for e in all_events if e['type'] == 'frame_sync')
    draw_count = sum(1 for e in all_events if e['type'] == 'draw_string')
    clear_count = sum(1 for e in all_events if e['type'] == 'clear_string')
    timed_count = sum(1 for e in all_events if e['type'] == 'timed_string')
    print(f"  {prg_name}: {sync_count} syncs, {draw_count} draws, "
          f"{clear_count} clears, {timed_count} timed")

    subs = events_to_subtitles(all_events)
    if subs:
        # Assign subtitles to the first CPK referenced by this PRG.
        # Most PRGs control exactly one FMV. Multi-CPK PRGs would need
        # splitting by frame range, which we can add later if needed.
        cpk_name = cpk_refs[0][1]
        results[cpk_name] = subs
        print(f"  {prg_name}: {len(subs)} subtitle(s) -> {cpk_name}")

    return results


# ---------------------------------------------------------------------------
# MOVIE.DAT fallback extraction
# ---------------------------------------------------------------------------

def extract_cpk_list_from_prg(prg_data):
    """Extract ordered CPK filename list from MOVIE.PRG."""
    return [m.decode().upper()
            for m in re.findall(rb'[\w_-]+\.[Cc][Pp][Kk]', prg_data)]


def detect_movie_dat_base(data):
    """Detect base address for MOVIE.DAT string pointers."""
    for known in [b"What's up, Edge", b"Thousands of years",
                  b"The age started anew", b"the Empire"]:
        str_offset = data.find(known)
        if str_offset == -1:
            continue
        candidates = Counter()
        for i in range(0, min(len(data) - 4, 0x2000), 4):
            val = read_u32_be(data, i)
            potential_base = val - str_offset
            if ((0x06000000 <= potential_base <= 0x060FFFFF) or
                    (0x00200000 <= potential_base <= 0x002FFFFF)):
                if potential_base % 0x10 == 0:
                    candidates[potential_base] += 1
        if candidates:
            if 0x00250000 in candidates:
                return 0x00250000
            return candidates.most_common(1)[0][0]
    return 0x00250000


def extract_from_movie_dat(dat_data, cpk_names):
    """Parse MOVIE.DAT subtitle table.

    MOVIE.DAT has a flat table of 8-byte entries:
        u16 start_frame, u16 end_frame, u32 string_pointer
    Groups are delimited by 0xFFFF sentinels and map 1:1 to CPKs.

    Returns dict: {cpk_name: [subtitle_entries]}.
    """
    base = detect_movie_dat_base(dat_data)
    print(f"  MOVIE.DAT: base=0x{base:08X}")

    groups = []
    current_group = []
    i = 0

    while i < len(dat_data) - 8:
        if dat_data[i:i+2] == b'\xFF\xFF':
            if current_group:
                groups.append(current_group)
                current_group = []
            i += 8
            continue

        start_frame = read_u16_be(dat_data, i)
        end_frame = read_u16_be(dat_data, i + 2)
        ptr = read_u32_be(dat_data, i + 4)

        if base <= ptr < base + len(dat_data):
            str_off = ptr - base
            text = read_cstring(dat_data, str_off)
            if text and len(text) >= 2:
                current_group.append({
                    'start_frame': start_frame,
                    'end_frame': end_frame,
                    'text': text
                })
            i += 8
        else:
            break

    if current_group:
        groups.append(current_group)

    print(f"  MOVIE.DAT: {len(groups)} subtitle group(s)")

    # Map groups to CPK names in order (1:1)
    results = {}
    for idx, group in enumerate(groups):
        if idx < len(cpk_names):
            name = cpk_names[idx]
            # Normalise: ensure it has .CPK extension
            if not name.upper().endswith('.CPK'):
                name = name + '.CPK'
            results[name.upper()] = group
        else:
            results[f'GROUP_{idx:02d}.CPK'] = group

    return results


# ---------------------------------------------------------------------------
# SRT output
# ---------------------------------------------------------------------------

def write_srt(filepath, subtitles, fps=15.0):
    """Write subtitle list to SRT file."""
    with open(filepath, 'w', encoding='utf-8') as f:
        for idx, sub in enumerate(subtitles):
            start_ts = frame_to_srt_ts(sub['start_frame'], fps)
            end_ts = frame_to_srt_ts(sub['end_frame'], fps)
            f.write(f"{idx + 1}\n")
            f.write(f"{start_ts} --> {end_ts}\n")
            f.write(f"{sub['text']}\n\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract FMV subtitles from PDS PRG overlays and MOVIE.DAT")
    parser.add_argument('--iso', required=True,
                        help="Path to PDS disc image (raw BIN/ISO)")
    parser.add_argument('--output', default='output/subtitles',
                        help="Output directory for SRT files")
    parser.add_argument('--fps', type=float, default=15.0,
                        help="FMV frame rate (default: 15)")
    parser.add_argument('--verbose', '-v', action='store_true',
                        help="Verbose output")
    parser.add_argument('--method', choices=['prg', 'dat', 'both'],
                        default='both',
                        help="Extraction method: prg (bytecode parser), "
                             "dat (MOVIE.DAT table), or both (PRG primary, "
                             "DAT fallback for uncovered CPKs)")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    iso = ISO9660Reader(args.iso)
    files = iso.list_files()

    prg_entries = [f for f in files if f['name'].upper().endswith('.PRG')]
    cpk_entries = [f for f in files if f['name'].upper().endswith('.CPK')]
    cpk_names_on_disc = set(f['name'].upper() for f in cpk_entries)

    print(f"Disc: {len(prg_entries)} PRG files, {len(cpk_entries)} CPK files")

    all_subtitles = {}  # cpk_name -> [subtitle entries]

    # -------------------------------------------------------------------
    # Phase 1: PRG bytecode extraction
    # -------------------------------------------------------------------
    if args.method in ('prg', 'both'):
        print("\n=== Phase 1: PRG bytecode extraction ===")

        for entry in prg_entries:
            prg_data = iso.extract_file(entry['lba'], entry['size'])

            # Skip files with no CPK references
            if not re.search(rb'\.[Cc][Pp][Kk]', prg_data):
                continue
            # Skip MOVIE.PRG — it's a CPK playlist, not a scene script
            if entry['name'].upper() == 'MOVIE.PRG':
                continue

            result = extract_from_prg(prg_data, entry['name'])
            for cpk_name, subs in result.items():
                if cpk_name in cpk_names_on_disc:
                    all_subtitles[cpk_name] = subs

    # -------------------------------------------------------------------
    # Phase 2: MOVIE.DAT fallback
    # -------------------------------------------------------------------
    if args.method in ('dat', 'both'):
        cpks_covered = set(all_subtitles.keys())
        cpks_needing = cpk_names_on_disc - cpks_covered

        if args.method == 'dat' or cpks_needing:
            print(f"\n=== Phase 2: MOVIE.DAT fallback ===")
            if cpks_needing and args.method == 'both':
                print(f"  CPKs not covered by PRG: {sorted(cpks_needing)}")

            dat_entry = next((f for f in files
                              if f['name'].upper() == 'MOVIE.DAT'), None)
            movie_prg = next((f for f in files
                              if f['name'].upper() == 'MOVIE.PRG'), None)

            if dat_entry:
                dat_data = iso.extract_file(dat_entry['lba'],
                                            dat_entry['size'])
                cpk_order = []
                if movie_prg:
                    prg_data = iso.extract_file(movie_prg['lba'],
                                                movie_prg['size'])
                    cpk_order = extract_cpk_list_from_prg(prg_data)
                    print(f"  MOVIE.PRG CPK order ({len(cpk_order)}): "
                          f"{cpk_order[:5]}...")
                if not cpk_order:
                    cpk_order = sorted(cpk_names_on_disc)

                dat_results = extract_from_movie_dat(dat_data, cpk_order)

                for cpk_name, subs in dat_results.items():
                    if args.method == 'dat':
                        # DAT-only mode: use all DAT results
                        all_subtitles[cpk_name] = subs
                    elif cpk_name not in all_subtitles:
                        # Both mode: only use DAT for uncovered CPKs
                        all_subtitles[cpk_name] = subs
                        print(f"  DAT fallback: {cpk_name} "
                              f"({len(subs)} subtitle(s))")
            else:
                print("  MOVIE.DAT not found on disc")

    iso.close()

    # -------------------------------------------------------------------
    # Phase 3: Write SRT files
    # -------------------------------------------------------------------
    print(f"\n=== Writing SRT files ===")

    written = 0
    for cpk_name in sorted(all_subtitles.keys()):
        subs = all_subtitles[cpk_name]
        if not subs:
            continue

        base_name = os.path.splitext(cpk_name)[0]
        srt_path = os.path.join(args.output, f"{base_name}.srt")
        write_srt(srt_path, subs, args.fps)
        print(f"  {srt_path} ({len(subs)} subtitle(s))")
        written += 1

        if args.verbose:
            for s in subs[:3]:
                print(f"    [{s['start_frame']:>5d}-{s['end_frame']:>5d}] "
                      f"{s['text'][:60]}")
            if len(subs) > 3:
                print(f"    ... and {len(subs) - 3} more")

    print(f"\nDone: {written} SRT file(s) written to {args.output}/")

    if not written:
        print("\nWARNING: No subtitles extracted!")
        print("Try: --method dat  or  --method prg  to isolate the issue")
        print("Run with --verbose for more details")


if __name__ == '__main__':
    main()