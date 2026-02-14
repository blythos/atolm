import sys
import os

# Add tools directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'tools'))
from common.iso9660 import ISO9660Reader
import re

def extract_cpk_list_from_prg(prg_data):
    """Extract ordered CPK filename list from MOVIE.PRG."""
    return [m.decode().upper()
            for m in re.findall(rb'[\w_-]+\.[Cc][Pp][Kk]', prg_data)]

def main():
    iso_path = "ISOs/Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin"
    iso = ISO9660Reader(iso_path)
    files = iso.list_files()

    # 1. Get CPK List from MOVIE.PRG
    movie_prg = next((f for f in files if f['name'].upper() == 'MOVIE.PRG'), None)
    if not movie_prg:
        print("MOVIE.PRG not found")
        return

    prg_data = iso.extract_file(movie_prg['lba'], movie_prg['size'])
    cpk_list = extract_cpk_list_from_prg(prg_data)
    print(f"MOVIE.PRG: Found {len(cpk_list)} CPKs")
    
    # 2. Inspect MOVIE.DAT structure
    movie_dat = next((f for f in files if f['name'].upper() == 'MOVIE.DAT'), None)
    if not movie_dat:
        print("MOVIE.DAT not found")
        return

try:
    from tools.extract_subtitles import read_u16_be, read_u32_be, read_cstring, detect_movie_dat_base
except ImportError:
    # Quick mock if import fails (unlikely in this env but safe)
    def read_u16_be(b, o): return (b[o] << 8) | b[o+1]
    def read_u32_be(b, o): return (b[o] << 24) | (b[o+1] << 16) | (b[o+2] << 8) | b[o+3]
    def read_cstring(b, o):
        end = b.find(b'\x00', o)
        return b[o:end].decode('latin-1', errors='ignore') if end != -1 else ""
    def detect_movie_dat_base(d): return 0x00250000

def main():
    iso_path = "ISOs/Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin"
    iso = ISO9660Reader(iso_path)
    files = iso.list_files()

    # 1. Get CPK List from MOVIE.PRG
    movie_prg = next((f for f in files if f['name'].upper() == 'MOVIE.PRG'), None)
    if not movie_prg:
        print("MOVIE.PRG not found")
        return

    prg_data = iso.extract_file(movie_prg['lba'], movie_prg['size'])
    cpk_list = extract_cpk_list_from_prg(prg_data)
    
    # 2. Inspect MOVIE.DAT structure
    movie_dat = next((f for f in files if f['name'].upper() == 'MOVIE.DAT'), None)
    if not movie_dat:
        print("MOVIE.DAT not found")
        return

    dat_data = iso.extract_file(movie_dat['lba'], movie_dat['size'])
    base = detect_movie_dat_base(dat_data)
    
    i = 0
    group_idx = 0
    entries_in_group = 0
    first_string = None
    
    print("\nScanning MOVIE.DAT groups:")
    while i < len(dat_data) - 8:
        # Check for terminator
        if dat_data[i:i+2] == b'\xFF\xFF':
            print(f"Group {group_idx}: {entries_in_group} entries. Sample: \"{first_string}\"")
            if group_idx < len(cpk_list):
                 print(f"  (Index {group_idx} in PRG: {cpk_list[group_idx]})")
            
            group_idx += 1
            entries_in_group = 0
            first_string = None
            i += 8 
            continue
        
        # Read entry
        ptr = read_u32_be(dat_data, i + 4)
        if base <= ptr < base + len(dat_data):
            if first_string is None:
                first_string = read_cstring(dat_data, ptr - base)
        else:
            # End of table
            break
            
        entries_in_group += 1
        i += 8

    # Process last group if any
    if entries_in_group > 0:
         print(f"Group {group_idx}: {entries_in_group} entries. Sample: \"{first_string}\"")

    print(f"\nTotal Groups Found: {group_idx + 1}")
    print(f"Total CPKs in PRG: {len(cpk_list)}")

if __name__ == "__main__":
    main()
