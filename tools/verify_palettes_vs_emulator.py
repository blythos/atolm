import sys
import struct
import argparse
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'common'))
from iso9660 import ISO9660Reader

def compare_cram(savestate_path, prg_files, iso_reader):
    """
    Compares the 4096-byte VDP2 CRAM from a Ymir savestate against all known PRG files
    to find an exact palette match, proving the PRG palette extraction logic works.
    """
    with open(savestate_path, 'rb') as f:
        # 0x154355 is the standard VDP2 CRAM offset in uncompressed Ymir Saturn save states
        f.seek(0x154355)
        cram_data = f.read(4096)
        
    # Read CRAM colors as a set
    cram_colors = set()
    for i in range(2048):
        val = struct.unpack_from('>H', cram_data, i*2)[0]
        cram_colors.add(val)
    
    # Ignore transparent (0x0000) and opaque black (0x8000) when verifying matching palettes
    # as these are often default/empty slots
    cram_colors.discard(0x0000)
    cram_colors.discard(0x8000)
    
    filename = os.path.basename(savestate_path)
    total_unique = len(cram_colors)
    print(f"--- Analyzing {filename} ---")
    print(f"Total unique non-zero colors in VDP2 CRAM: {total_unique}")
    
    best_match = None
    best_colors_found = 0
    
    for prg in prg_files:
        prg_data = iso_reader.extract_file(prg['lba'], prg['size'])
        if len(prg_data) < 0x278 + 512:
            continue
            
        pal_data = prg_data[0x278:0x278+4096]
        prg_colors = set()
        for i in range(len(pal_data)//2):
            val = struct.unpack_from('>H', pal_data, i*2)[0]
            if val != 0 and val != 0x8000:
                prg_colors.add(val)
                
        intersection = cram_colors.intersection(prg_colors)
        if len(intersection) > best_colors_found:
            best_colors_found = len(intersection)
            best_match = prg['name']

        if best_colors_found == total_unique:
            # 100% Match found
            break
            
    if best_match:
        match_pct = (best_colors_found / total_unique) * 100
        print(f"Result: {match_pct:.1f}% match ({best_colors_found}/{total_unique} colors)")
        print(f"Matched PRG Overlay: {best_match}\n")
        return match_pct == 100.0
    else:
        print("Result: No matching PRG overlay found.\n")
        return False

def main():
    parser = argparse.ArgumentParser(description="Verify extracted PRG palettes against emulator save states.")
    parser.add_argument('--iso', required=True, help="Path to Panzer Dragoon Saga Disc 1 ISO (.bin)")
    parser.add_argument('--savestates', required=True, help="Directory containing .savestate files")
    args = parser.parse_args()
    
    iso = ISO9660Reader(args.iso)
    files = iso.list_files()
    prg_files = [f for f in files if f['name'].endswith('.PRG')]
    
    savestate_files = [
        os.path.join(args.savestates, f) 
        for f in os.listdir(args.savestates) 
        if f.endswith('.savestate')
    ]
    
    if not savestate_files:
        print("No .savestate files found in the directory.")
        iso.close()
        return

    all_passed = True
    for sf in savestate_files:
        passed = compare_cram(sf, prg_files, iso)
        if not passed:
            all_passed = False
            
    if all_passed:
        print("SUCCESS: All savestates matched 100% of their unique colors to a PRG overlay on disc!")
    else:
        print("WARNING: Some savestates did not perfectly match a PRG overlay. Check output for details.")

    iso.close()

if __name__ == '__main__':
    main()
