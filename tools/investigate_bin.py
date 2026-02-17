import struct
import os

def investigate(bin_path):
    with open(bin_path, 'rb') as f:
        data = f.read()
    
    # 1. Look for the descriptor with SA=0x2
    print(f"--- Investigating {bin_path} ---")
    descriptors = []
    for i in range(0, 4096, 2):
        if i + 32 > len(data): break
        slot0 = struct.unpack('>H', data[i:i+2])[0]
        mode = (slot0 >> 11) & 0x03
        if mode in [0, 1]:
            sa_high = data[i+3] & 0x03
            sa_low = struct.unpack('>H', data[i+4:i+6])[0]
            sa = (sa_high << 16) | sa_low
            
            lea_high = data[i+7] & 0x03
            lea_low = struct.unpack('>H', data[i+8:i+10])[0]
            lea = (lea_high << 16) | lea_low
            
            if sa < 0x100: # Look for samples at the start
                 descriptors.append({'ptr': i, 'sa': sa, 'lea': lea, 'mode': mode, 'data': data[i:i+32]})

    descriptors.sort(key=lambda x: x['sa'])
    for d in descriptors:
        print(f"Offset {hex(d['ptr'])}: SA={hex(d['sa'])}, LEA={hex(d['lea'])}, Mode={d['mode']}")
        # print(f"  Hex: {d['data'].hex(' ')}")

    # 2. Look at the start of the file for PCM data pattern
    # PCM often starts after the headers. Let's look at 0x200, 0x400, 0x600...
    for p_start in [0x200, 0x240, 0x400, 0x600]:
        print(f"Data at {hex(p_start)}: {data[p_start:p_start+16].hex(' ')}")

if __name__ == "__main__":
    investigate('output/seq_extract/raw/A3BGM2.BIN')
    investigate('output/seq_extract/raw/KOGATA.BIN')
