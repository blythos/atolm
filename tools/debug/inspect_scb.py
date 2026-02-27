import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'common'))
from iso9660 import ISO9660Reader
import struct

def decode_pattern_name(val):
    return val & 0x3FF

iso = ISO9660Reader(r"e:\Dev\atolm\ISOs\Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin")
files = iso.list_files()

pnb_files = {f['name']: f for f in files if f['name'].endswith('.PNB')}
scb_files = {f['name']: f for f in files if f['name'].endswith('.SCB')}

print("Analyzing pairings...")
for pnb_name, pnb_f in pnb_files.items():
    scb_name = pnb_name[:-4] + '.SCB'
    if scb_name in scb_files:
        scb_f = scb_files[scb_name]
        
        pnb_data = iso.extract_file(pnb_f['lba'], pnb_f['size'])
        if len(pnb_data) < 2: continue
        count = len(pnb_data) // 2
        entries = struct.unpack('>%dH' % count, pnb_data)
        max_char = max(decode_pattern_name(e) for e in entries)
        
        scb_size = scb_f['size']
        expected_tiles = max_char + 1
        
        # 16x16 tiles
        bytes_4bpp = expected_tiles * 128
        bytes_8bpp = expected_tiles * 256
        
        bpp = "?"
        if scb_size >= bytes_8bpp and scb_size < bytes_8bpp + 5000:
            bpp = "8"
        elif scb_size >= bytes_4bpp and scb_size < bytes_4bpp + 5000:
            bpp = "4"
        elif scb_size >= bytes_8bpp:
            bpp = "8 (large)"
        elif scb_size >= bytes_4bpp:
            bpp = "4 (large)"
            
        print(f"{pnb_name:15s} max_char={max_char:4d} scb_size={scb_size:8d} => {bpp}bpp (4: {bytes_4bpp}, 8: {bytes_8bpp})")

iso.close()
