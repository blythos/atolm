from tools.common.iso9660 import ISO9660Reader
import argparse

def main():
    parser = argparse.ArgumentParser(description="Inspect ISO/BIN file contents.")
    parser.add_argument("iso_path", help="Path to disc image")
    args = parser.parse_args()
    
    iso_path = args.iso_path
    print(f"Opening {iso_path}")
    
    try:
        iso = ISO9660Reader(iso_path)
    except Exception as e:
        print(f"Error opening ISO: {e}")
        return
    
    print("Files found (raw scan):")
    files = iso.list_files()
    for f in files:
        print(f"  {f['name']} (Size: {f['size']}, LBA: {f['lba']})")
        
    print(f"\nTotal files: {len(files)}")
    
    # Check for CPKs
    found_cpks = set(f['name'].upper() for f in files if f['name'].upper().endswith('.CPK'))
    print(f"\nFound {len(found_cpks)} CPKs.")

if __name__ == "__main__":
    main()
