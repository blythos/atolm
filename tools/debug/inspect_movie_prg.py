import sys
import os

# Add tools directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'tools'))
from common.iso9660 import ISO9660Reader
import re

def main():
    iso_path = "ISOs/Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin"
    iso = ISO9660Reader(iso_path)
    files = iso.list_files()
    movie_prg = next((f for f in files if f['name'].upper() == 'MOVIE.PRG'), None)
    
    data = iso.extract_file(movie_prg['lba'], movie_prg['size'])
    
    # regex for CPK
    matches = list(re.finditer(rb'[\w_-]+\.[Cc][Pp][Kk]', data))
    
    print(f"Found {len(matches)} CPK references in MOVIE.PRG")
    
    for i, m in enumerate(matches):
        name = m.group().decode()
        start = m.start()
        end = m.end()
        
        # Look at bytes before and after
        before = data[max(0, start-16):start]
        after = data[end:min(len(data), end+16)]
        
        print(f"\n{i}: {name}")
        print(f"  Before: {before.hex(' ')}")
        print(f"  After:  {after.hex(' ')}")

if __name__ == "__main__":
    main()
