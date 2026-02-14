import hashlib
import os
import glob
from tools.common.iso9660 import ISO9660Reader
from tools.extract_subtitles import extract_cpk_list_from_prg

def get_file_hash(data):
    return hashlib.md5(data).hexdigest()

def main():
    iso_dir = "ISOs"
    # Find one ISO per disc
    patterns = [
        "*Disc 1*Track 1*.bin",
        "*Disc 2*Track 1*.bin",
        "*Disc 3*Track 1*.bin",
        "*Disc 4*Track 1*.bin"
    ]
    
    isos = []
    for p in patterns:
        matches = glob.glob(os.path.join(iso_dir, p))
        if matches:
            isos.append(matches[0])
            
    print(f"Found {len(isos)} ISOs to compare.")
    
    dat_hashes = {}
    prg_hashes = {}
    prg_lists = {}
    
    for iso_path in isos:
        disc_name = os.path.basename(iso_path)
        print(f"Reading {disc_name}...")
        try:
            iso = ISO9660Reader(iso_path)
            files = iso.list_files()
            
            # MOVIE.DAT
            dat_file = next((f for f in files if f['name'].upper() == 'MOVIE.DAT'), None)
            if dat_file:
                data = iso.extract_file(dat_file['lba'], dat_file['size'])
                h = get_file_hash(data)
                dat_hashes[disc_name] = h
                print(f"  MOVIE.DAT: {dat_file['size']} bytes, Hash: {h}")
            else:
                print(f"  MOVIE.DAT: Not Found")

            # MOVIE.PRG
            prg_file = next((f for f in files if f['name'].upper() == 'MOVIE.PRG'), None)
            if prg_file:
                data = iso.extract_file(prg_file['lba'], prg_file['size'])
                h = get_file_hash(data)
                prg_hashes[disc_name] = h
                
                # Extract list
                cpk_list = extract_cpk_list_from_prg(data)
                prg_lists[disc_name] = cpk_list
                print(f"  MOVIE.PRG: {prg_file['size']} bytes, Hash: {h}, Entries: {len(cpk_list)}")
                for i, name in enumerate(cpk_list):
                    print(f"    {i:02d}: {name}")
            else:
                print(f"  MOVIE.PRG: Not Found")
                
            iso.close()
        except Exception as e:
            print(f"  Error: {e}")

    # Analysis
    print("\n--- Analysis ---")
    
    # Check DAT
    first_hash = list(dat_hashes.values())[0] if dat_hashes else None
    all_dat_same = all(h == first_hash for h in dat_hashes.values())
    print(f"MOVIE.DAT Identical across all discs? {all_dat_same}")
    
    # Check PRG
    first_prg = list(prg_hashes.values())[0] if prg_hashes else None
    all_prg_same = all(h == first_prg for h in prg_hashes.values())
    print(f"MOVIE.PRG Identical across all discs? {all_prg_same}")

if __name__ == "__main__":
    main()
