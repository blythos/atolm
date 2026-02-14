import os
import sys
import struct
import argparse
import re
from collections import Counter

# Add tools directory to path to import common
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from tools.common.iso9660 import ISO9660Reader
except ImportError:
    # Fallback if running from tools root
    sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'common'))
    from iso9660 import ISO9660Reader

def read_u16_be(data, offset):
    return struct.unpack('>H', data[offset:offset+2])[0]

def read_u32_be(data, offset):
    return struct.unpack('>I', data[offset:offset+4])[0]

def read_string(data, offset):
    s = b""
    while offset < len(data):
        c = data[offset]
        if c == 0: break
        s += bytes([c])
        offset += 1
    return s.decode('ascii', errors='ignore')

def detect_base_address(data):
    known_str = b"What's up, Edge"
    str_offset = data.find(known_str)
    
    if str_offset == -1:
        known_str = b"Thousands of years"
        str_offset = data.find(known_str)

    candidate_bases = []
    if str_offset != -1:
        for i in range(0, len(data) - 4, 4):
            val = read_u32_be(data, i)
            potential_base = val - str_offset
            if (0x06000000 <= potential_base <= 0x060FFFFF) or (0x00200000 <= potential_base <= 0x002FFFFF):
                 if potential_base % 0x10 == 0:
                     candidate_bases.append(potential_base)
                     
    if candidate_bases:
        if 0x00250000 in candidate_bases: return 0x00250000
        return Counter(candidate_bases).most_common(1)[0][0]
        
    return 0x00250000

def time_to_srt_timestamp(seconds):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    ms = (s - int(s)) * 1000
    return f"{int(h):02}:{int(m):02}:{int(s):02},{int(ms):03}"

def extract_cpk_list(prg_data):
    # Find all strings ending in .CPK
    return [m.decode().upper() for m in re.findall(b'[\w-]+\.[Cc][Pp][Kk]', prg_data)]

def main():
    parser = argparse.ArgumentParser(description="Extract Subtitles from MOVIE.DAT Table")
    parser.add_argument('--iso', required=True, help="Path to PDS Disc 1 ISO/BIN")
    parser.add_argument('--output', default="output/subtitles", help="Output folder")
    parser.add_argument('--fps', type=float, default=15.0, help="Frame rate (15 for FMV)")
    parser.add_argument('--frame-offset', type=int, default=-15, help="Offset to apply to frame numbers (default -15 for ~1s fix)")
    args = parser.parse_args()
    
    if not os.path.exists(args.output):
        os.makedirs(args.output)
        
    iso = ISO9660Reader(args.iso)
    files = iso.list_files()
    
    # 1. Get MOVIE.DAT (Subtitles)
    try:
        dat_entry = next(f for f in files if f['name'].upper() == 'MOVIE.DAT')
    except StopIteration:
        print("Error: MOVIE.DAT not found.")
        return
    dat_data = iso.extract_file(dat_entry['lba'], dat_entry['size'])

    # 2. Get MOVIE.PRG (CPK list)
    try:
        prg_entry = next(f for f in files if f['name'].upper() == 'MOVIE.PRG')
        prg_data = iso.extract_file(prg_entry['lba'], prg_entry['size'])
        cpk_names = extract_cpk_list(prg_data)
        print(f"Extracted {len(cpk_names)} CPK names from MOVIE.PRG")
    except StopIteration:
        print("Warning: MOVIE.PRG not found. Files will be named by index.")
        cpk_names = []
        
    iso.close()
    
    base = detect_base_address(dat_data)
    print(f"Detected Base Address: 0x{base:08X}")
    
    groups = []
    current_group = []
    
    # The table is at the start of the file.
    # Entry size = 8 bytes: StartFrame(2), EndFrame(2), Pointer(4)
    i = 0
    while i < len(dat_data) - 8:
        # PDS sentinel for end of table group
        if dat_data[i:i+2] == b'\xFF\xFF':
            if current_group:
                groups.append(current_group)
                current_group = []
            i += 8
            continue
            
        start_frame = max(0, read_u16_be(dat_data, i) + args.frame_offset)
        end_frame = max(0, read_u16_be(dat_data, i + 2) + args.frame_offset)
        ptr = read_u32_be(dat_data, i + 4)
        
        # Validation: ptr must be valid
        if base <= ptr < base + len(dat_data):
            str_off = ptr - base
            text = read_string(dat_data, str_off)
            if text:
                current_group.append({
                    'start_frame': start_frame,
                    'end_frame': end_frame,
                    'text': text
                })
            i += 8
        else:
            # End of table area?
            break
            
    if current_group:
        groups.append(current_group)

    print(f"Found {len(groups)} subtitle groups.")
    
    for idx, group in enumerate(groups):
        if idx < len(cpk_names):
            name = os.path.splitext(cpk_names[idx])[0]
        else:
            name = f"Group_{idx:02d}"
            
        srt_path = os.path.join(args.output, f"{name}.srt")
        with open(srt_path, 'w', encoding='utf-8') as f:
            for s_idx, sub in enumerate(group):
                start_sec = sub['start_frame'] / args.fps
                end_sec = sub['end_frame'] / args.fps
                
                # Boundary check: Ensure end >= start
                if end_sec <= start_sec:
                    end_sec = start_sec + 1.0 # Min duration

                f.write(f"{s_idx+1}\n")
                f.write(f"{time_to_srt_timestamp(start_sec)} --> {time_to_srt_timestamp(end_sec)}\n")
                f.write(f"{sub['text']}\n\n")
        print(f"Saved {srt_path} ({len(group)} lines)")


if __name__ == '__main__':
    main()
