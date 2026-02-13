import sys
import struct

SECTOR_SIZE = 2352

def main():
    if len(sys.argv) < 3:
        print("Usage: debug_sector.py <bin_path> <lba>")
        return
        
    bin_path = sys.argv[1]
    lba = int(sys.argv[2])
    
    with open(bin_path, 'rb') as f:
        f.seek(lba * SECTOR_SIZE)
        raw = f.read(SECTOR_SIZE)
        
        print(f"Sector {lba} Dump:")
        print(f"Header: {raw[:16].hex()}")
        print(f"Mode (Offset 15): {raw[15]}")
        
        if raw[15] == 2:
            print(f"Subheader (Offset 16-23): {raw[16:24].hex()}")
            print(f"Submode (Offset 18): {raw[18]:02x}")
            
            if raw[18] & 0x20:
                print("Type: Mode 2 Form 2 (2324 bytes payload)")
            else:
                print("Type: Mode 2 Form 1 (2048 bytes payload)")
        elif raw[15] == 1:
            print("Type: Mode 1 (2048 bytes payload)")
            
if __name__ == "__main__":
    main()
