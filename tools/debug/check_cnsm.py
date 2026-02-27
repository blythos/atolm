import struct

with open(r"e:\Dev\atolm\output\WARNING.PNB", "rb") as f:
    data = f.read()

entries = struct.unpack(f">{len(data)//2}H", data)
print(f"Total entries: {len(entries)}")
print(f"Max 10-bit char: {max(e & 0x3FF for e in entries)}")
print(f"Max 12-bit char: {max(e & 0xFFF for e in entries)}")
