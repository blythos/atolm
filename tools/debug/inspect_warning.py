with open(r"e:\Dev\atolm\output\WARNING.SCB", "rb") as f:
    data = f.read()

print(f"File size: {len(data)}")
nonzero_bytes = sum(1 for b in data if b != 0)
print(f"Non-zero bytes: {nonzero_bytes}")

for i in range(128*10, 128*11, 16):
    chunk = data[i:i+16]
    print(f"{i:04x}: " + " ".join(f"{b:02x}" for b in chunk))
