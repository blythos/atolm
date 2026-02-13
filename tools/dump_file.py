import sys
import os
import struct

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from tools.common.iso9660 import ISO9660Reader

def hex_dump(data, start=0, length=None):
    if length is None: length = len(data)
    end = min(start + length, len(data))
    
    for i in range(start, end, 16):
        chunk = data[i:min(i+16, end)]
        hex_str = ' '.join(f'{b:02X}' for b in chunk)
        ascii_str = ''.join((chr(b) if 32 <= b < 127 else '.') for b in chunk)
        print(f'{i:04X}: {hex_str:<48} | {ascii_str}')

def main():
    if len(sys.argv) < 3:
        print("Usage: python dump_file.py <iso_path> <filename>")
        sys.exit(1)
        
    iso_path = sys.argv[1]
    filename = sys.argv[2]
    
    iso = ISO9660Reader(iso_path)
    try:
        files = iso.list_files()
        target = next((f for f in files if f['name'] == filename), None)
        
        if not target:
            print(f"File {filename} not found.")
            sys.exit(1)
            
        print(f"Dumping {filename} ({target['size']} bytes)...")
        data = iso.extract_file(target['lba'], target['size'])
        hex_dump(data)
    finally:
        iso.close()

if __name__ == '__main__':
    main()
