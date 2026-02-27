import struct

with open(r"e:\Dev\atolm\output\WARNING.PNB", "rb") as f:
    pnb_data = f.read()

entries = struct.unpack(f">{len(pnb_data)//2}H", pnb_data)
width_tiles = 64
height_tiles = len(entries) // width_tiles

for ty in range(6, 20):
    row_str = ""
    for tx in range(2, 26):
        val = entries[ty * width_tiles + tx]
        char_idx = val & 0xFFF
        
        if char_idx >= 512:
            idx = char_idx - 512
            if idx == 0:
                row_str += " . " # transparent
            else:
                row_str += f"{idx:03x} "
        else:
            row_str += "--- "
            
    print(f"Row {ty:02d}: {row_str}")
