import os
import sys
import argparse
import json
from common.iso9660 import ISO9660Reader, read_sector

# Monkey-patch ISO9660Reader to support extraction if not present
if not hasattr(ISO9660Reader, 'extract_file'):
    def extract_file(self, lba, size, output_path):
        """Extract a file given its LBA and size."""
        num_sectors = (size + 2048 - 1) // 2048
        self.f.seek(lba * 2048)
        data = b''
        for i in range(num_sectors):
            data += read_sector(self.f, lba + i)
        
        with open(output_path, 'wb') as f:
            f.write(data[:size])
    
    ISO9660Reader.extract_file = extract_file

TRACK_NAMES = [
    "A3 1 (MAP)", "A3 2 (MAP)", "A3 (MAP)", "A3 (ZAKO)", "A3 2 (ZAKO)", "A3 (MBOS)",
    "A5 (MAP)", "A5 (ZAKO)", "A5 (MBOS)", "A5 (BOSS)",
    "A7 (MAP)", "A7 (ZAKO)", "A7 (MBOS)", "A7 (BOSS)",
    "B1 (MAP)", "B1 (ZAKO)", "B3 (MAP)",
    "B2 1 (MAP)", "B2 2 (MAP)", "B2 (MBOS)", "B2 (BOSS)",
    "B5 1 (MAP)", "B5 (ZAKO)", "B5 2 (ZAKO)", "B5 3 (ZAKO)", "B5 (MBOS)", "B5 (BOSS)",
    "B6 (MAP)", "B6 (ZAKO)", "B6 (MBOS)", "B6 (BOSS)",
    "C2 (MAP)", "C2 (ZAKO)", "C2 (MBOS)", "C2 (BOSS)",
    "C4 (MAP)", "C4 (ZAKO)", "C4 (MBOS)",
    "C5 (ZAKO)", "C5 (MBOS)", "C5 (BOSS)",
    "C8 (MAP)", "C8 (ZAKO)", "C8 (BOSS)",
    "D2 (MAP)", "D2 (BOSS)", "D3 (MAP)",
    "D4 (MAP)", "D4 (ZAKO)", "D4 (MBOS)",
    "D5 (MAP)", "D5 1 (MBOS)", "D5 2 (MBOS)", "D5 (BOSS)",
    "AD", "HANU", "RUIN", "EXCA", "TOWN", "PAET", "CARAVAN", "CAMP", "SEEKER",
    "EVENT 06", "EVENT 11", "EVENT 14", "EVENT 22", "EVENT 74", "EVENT 78", "EVENT 128",
    "TITLE", "DROGON 00", "DROGON 08", "EDGE", "EDGE2"
]

def scan_iso(iso_path):
    print(f"Scanning ISO: {iso_path}")
    reader = ISO9660Reader(iso_path)
    files = reader.list_files()
    
    seq_files = []
    snd_files = []
    bin_files = []
    
    for f in files:
        name = f['name'].upper()
        if name.endswith('.SEQ'):
            seq_files.append(f)
        elif '.SND' in name:
            snd_files.append(f)
        elif name.endswith('.BIN'):
            # Only consider .BIN files that might be tone banks
            # Heuristic: > 10KB and < 1MB (tone banks are usually in this range)
            if 1024 * 10 <= f['size'] <= 1024 * 1024:
                # Also exclude known non-audio types if we had a list, 
                # but for now we'll just keep them as candidates
                bin_files.append(f)
    
    print(f"Found {len(seq_files)} .SEQ files")
    print(f"Found {len(snd_files)} .SND files")
    print(f"Found {len(bin_files)} candidate .BIN files")
    
    # Heuristic pairing: Match .BIN to .SEQ if same dir and same base name
    catalog = {
        'standalone': [],
        'bundles': []
    }
    
    # Track which BINs we've paired
    paired_bins = set()
    
    for seq in seq_files:
        seq_path = seq['name']
        seq_dir = os.path.dirname(seq_path)
        seq_base = os.path.splitext(os.path.basename(seq_path))[0]
        
        match = None
        for bin_f in bin_files:
            bin_path = bin_f['name']
            bin_dir = os.path.dirname(bin_path)
            bin_base = os.path.splitext(os.path.basename(bin_path))[0]
            
            if bin_dir == seq_dir and bin_base == seq_base:
                match = bin_f
                paired_bins.add(bin_path)
                break
        
        catalog['standalone'].append({
            'seq': seq,
            'ton': match,
            'name': None # To be filled by heuristic or manual map
        })
        
    for snd in snd_files:
        catalog['bundles'].append(snd)

    # Simple naming heuristic based on standalone list order
    # Note: This is a guess as SNDTEST.PRG list order might not match dir scan order.
    # However, for now we just want the files.
        
    reader.close()
    return catalog

def main():
    parser = argparse.ArgumentParser(description='Panzer Dragoon Saga SEQ/TON Extractor')
    parser.add_argument('--iso', type=str, help='Path to Disc 1 ISO (.bin)')
    parser.add_argument('--scan', action='store_true', help='Scan ISO and list music files')
    parser.add_argument('--verbose', action='store_true', help='Print all files found')
    parser.add_argument('--output', type=str, help='Output directory (default: output/seq_extract)')
    parser.add_argument('--extract', action='store_true', help='Extract raw SEQ/TON files from ISO')
    
    args = parser.parse_args()
    
    output_dir = args.output or os.path.join('output', 'seq_extract')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    if args.scan:
        if not args.iso:
            print("Error: --iso required for scanning")
            return
            
        if args.verbose:
            reader = ISO9660Reader(args.iso)
            files = reader.list_files()
            for f in files:
                print(f"{f['name']} ({f['size']} bytes)")
            reader.close()
            print("-" * 40)

        catalog = scan_iso(args.iso)
        
        # Save catalog
        catalog_path = os.path.join(output_dir, 'music_catalog.json')
        with open(catalog_path, 'w') as f:
            json.dump(catalog, f, indent=4)
        print(f"\nCatalog saved to {catalog_path}")
        
        print("\n--- STANDALONE TRACKS ---")
        for entry in catalog['standalone']:
            seq_name = entry['seq']['name']
            ton_name = entry['ton']['name'] if entry['ton'] else "MISSING TON"
            print(f"SEQ: {seq_name} -> TON: {ton_name}")
            
        print("\n--- SOUND BUNDLES (.SND) ---")
        if not catalog['bundles']:
            print("No .SND bundles found.")
        else:
            for snd in catalog['bundles']:
                 print(snd['name'], f"({snd['size']} bytes)")

    if args.extract:
        if not args.iso:
            print("Error: --iso required for extraction")
            return
            
        print("\nExtracting raw files...")
        reader = ISO9660Reader(args.iso)
        
        # Load catalog if it exists, otherwise scan
        catalog_path = os.path.join(output_dir, 'music_catalog.json')
        if os.path.exists(catalog_path):
            with open(catalog_path, 'r') as f:
                catalog = json.load(f)
        else:
            catalog = scan_iso(args.iso)

        raw_dir = os.path.join(output_dir, 'raw')
        os.makedirs(raw_dir, exist_ok=True)

        for entry in catalog['standalone']:
            seq = entry['seq']
            ton = entry['ton']
            
            # Extract SEQ
            seq_out = os.path.join(raw_dir, os.path.basename(seq['name']))
            print(f"Extracting {seq['name']}...")
            reader.extract_file(seq['lba'], seq['size'], seq_out)
            
            # Extract TON if present
            if ton:
                ton_out = os.path.join(raw_dir, os.path.basename(ton['name']))
                print(f"Extracting {ton['name']}...")
                reader.extract_file(ton['lba'], ton['size'], ton_out)
        
        reader.close()
        print(f"Extraction complete. Files saved to {raw_dir}")

if __name__ == "__main__":
    main()
