import struct, os, sys
sys.path.insert(0, r'e:\Dev\atolm\tools\common')
from iso9660 import ISO9660Reader

in_dir = r'e:\Dev\atolm\output\cram_dumps'
cram_files = [f for f in os.listdir(in_dir) if f.endswith('.bin')]

cram_dumps = {}
for f in cram_files:
    with open(os.path.join(in_dir, f), 'rb') as fp:
        cram_dumps[f] = fp.read()

iso = ISO9660Reader(r'e:\Dev\atolm\ISOs\Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin')
all_files = iso.list_files()

# Only search PRG and DAT files
target_files = [f for f in all_files if f['name'].upper().endswith(('.PRG', '.DAT'))]
print(f'Scanning {len(target_files)} target files on disc for {len(cram_files)} CRAM dumps...\n')

# Let's read all target files into memory to speed up searches
file_cache = {}
for f in target_files:
    data = iso.extract_file(f['lba'], f['size'])
    if data:
        file_cache[f['name'].upper()] = data

for name, cram in cram_dumps.items():
    print(f'--- Analyzing {name} ---')
    found_matches = False
    
    # Check 512-byte blocks (full 8bpp palette)
    blocks_512 = []
    for i in range(8):
        b = cram[i*512:(i+1)*512]
        if not all(x == 0 for x in b):
            blocks_512.append((i*512, b))
            
    # Check 32-byte blocks (16-color 4bpp palette)
    blocks_32 = []
    for i in range(128):
        b = cram[i*32:(i+1)*32]
        # filter out mostly blank or identical bytes (needs at least 4 unique colors)
        if b.count(0) < 16 and len(set(b[::2])) > 4: 
            blocks_32.append((i*32, b))
            
    for fn, data in file_cache.items():
        file_matched = False
        for offset, block in blocks_512:
            idx = data.find(block)
            if idx != -1:
                print(f'  [512B] Found CRAM 0x{offset:03X} in {fn} at file offset 0x{idx:X}')
                file_matched = True
                found_matches = True
                
        if not file_matched:
            for offset, block in blocks_32:
                idx = data.find(block)
                if idx != -1:
                    print(f'  [ 32B] Found CRAM 0x{offset:03X} in {fn} at file offset 0x{idx:X}')
                    found_matches = True

    if not found_matches:
        print('  No matches found on disc.')
    print()

iso.close()
