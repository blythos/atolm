import os
import sys
import argparse
import json
from common.iso9660 import ISO9660Reader, read_sector

class ExtReader(ISO9660Reader):
    def extract_file(self, lba, size, output_path):
        """Extract a file given its LBA and size."""
        num_sectors = (size + 2048 - 1) // 2048
        self.f.seek(lba * 2048)
        data = b''
        for i in range(num_sectors):
            data += read_sector(self.f, lba + i)
        
        with open(output_path, 'wb') as f:
            f.write(data[:size])

def parse_sndtest_names(data):
    """Extract potential track names from SNDTEST.PRG data."""
    # Look for the block of names. They usually follow "NULL" and "COMMON".
    import re
    strings = re.findall(b'[\x20-\x7E]{4,}', data)
    names = []
    started = False
    for s in strings:
        name = s.decode('ascii', errors='ignore').strip()
        if name == "COMMON":
            started = True
            continue
        if started:
            # End of names block usually starts with things like "AD", "HANU", 
            # and then wraps up with "TITLE", "EDGE", etc.
            # Stop if we hit UI strings.
            if "Stop" in name or "Play" in name or "Volume" in name:
                break
            # Skip some known non-track strings if they appear
            if name in ["NULL", "PAUSE", "START", "HEADER", "PLAY"]:
                if len(names) > 30: # We expect ~75-80 names
                    break
                continue
            names.append(name)
    return names

def scan_iso(iso_path):
    print(f"Scanning ISO: {iso_path}")
    reader = ExtReader(iso_path)
    files = reader.list_files()
    
    seq_files = []
    snd_files = []
    bin_files = []
    sndtest_file = None
    
    for f in files:
        name = f['name'].upper()
        if name.endswith('.SEQ'):
            seq_files.append(f)
        elif '.SND' in name:
            snd_files.append(f)
        elif name.endswith('.BIN'):
            if 1024 * 10 <= f['size'] <= 1024 * 1024:
                bin_files.append(f)
        elif 'SNDTEST.PRG' in name:
            sndtest_file = f
    
    track_names = []
    if sndtest_file:
        print(f"Found {sndtest_file['name']}, extracting track names...")
        # Use a temp buffer or read it
        reader.f.seek(sndtest_file['lba'] * 2048)
        data = b''
        num_sectors = (sndtest_file['size'] + 2047) // 2048
        for i in range(num_sectors):
            data += read_sector(reader.f, sndtest_file['lba'] + i)
        track_names = parse_sndtest_names(data[:sndtest_file['size']])
        print(f"Extracted {len(track_names)} track names")

    print(f"Found {len(seq_files)} .SEQ files")
    print(f"Found {len(snd_files)} .SND files")
    print(f"Found {len(bin_files)} candidate .BIN files")
    
    catalog = {
        'named_tracks': [],
        'unnamed_tracks': [],
        'bundles': []
    }
    
    # Pairs
    pairs = []
    for seq in seq_files:
        seq_path = seq['name']
        seq_dir = os.path.dirname(seq_path)
        seq_base = os.path.splitext(os.path.basename(seq_path))[0]
        
        match = None
        for bin_f in bin_files:
            bin_path = bin_f['name']
            if os.path.dirname(bin_path) == seq_dir and os.path.splitext(os.path.basename(bin_path))[0] == seq_base:
                match = bin_f
                break
        pairs.append({'seq': seq, 'ton': match})

    # Sort by LBA to match game order heuristic
    pairs_sorted = sorted(pairs, key=lambda x: x['seq']['lba'])
    
    for i, pair in enumerate(pairs_sorted):
        if i < len(track_names):
            pair['name'] = track_names[i]
            catalog['named_tracks'].append(pair)
        else:
            catalog['unnamed_tracks'].append(pair)
        
    for snd in snd_files:
        catalog['bundles'].append(snd)
        
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
        
        print("\n--- NAMED TRACKS ---")
        for entry in catalog['named_tracks']:
            seq_name = entry['seq']['name']
            ton_name = entry['ton']['name'] if entry['ton'] else "MISSING TON"
            display_name = entry.get('name') or "Unknown"
            print(f"[{display_name}] SEQ: {seq_name} -> TON: {ton_name}")
            
        print("\n--- UNNAMED TRACKS ---")
        for entry in catalog['unnamed_tracks']:
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
        reader = ExtReader(args.iso)
        
        # Load catalog if it exists, otherwise scan
        catalog_path = os.path.join(output_dir, 'music_catalog.json')
        if os.path.exists(catalog_path):
            with open(catalog_path, 'r') as f:
                catalog = json.load(f)
        else:
            catalog = scan_iso(args.iso)

        raw_dir = os.path.join(output_dir, 'raw')
        os.makedirs(raw_dir, exist_ok=True)

        for section in ['named_tracks', 'unnamed_tracks']:
            for entry in catalog[section]:
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
