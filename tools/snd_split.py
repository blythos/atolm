"""
Panzer Dragoon Saga — SND Bundle Splitter & SEQ/BIN Catalogue Tool

Investigates and resolves the complete SEQ/BIN music file inventory across all
four PDS disc images. Handles:

  1. AREAMAP.SND parsing — the music area map table, a sequence of DMA-style
     load commands that the sound driver (SDDRVS.TSK on the 68000) uses to
     decide which tone banks and sequences to load into SCSP RAM for each
     in-game area. 276 bytes, terminated by 0xFF.

  2. SEQ->BIN pairing — matches each .SEQ sequence file to its .BIN tone bank.
     Primary method: exact base-name match (e.g. A3BGM.SEQ -> A3BGM.BIN).
     Fallback for the five known shared banks: LBA-proximity matching.
     Known shared banks:
       A3BGM1_1.SEQ  -> A3BGM.BIN
       A3BGM1_2.SEQ  -> A3BGM.BIN   (two sequences share one bank)
       BOSS01_2.SEQ  -> A3BOSS.BIN
       DRG_SE.SEQ    -> DRG1SE.BIN
       TITLE.SEQ     -> TITLEBGM.BIN

  3. Multi-disc extraction — catalogues and optionally extracts raw SEQ/BIN
     files from all four disc images, then invokes ton_to_wav.py and
     seq_to_midi.py for conversion.

Background: The task specification mentioned EPISODE1–4.SND and INTER12/23/35.SND
bundle archives with hardcoded sub-bank offsets. Those files do not appear in the
ISO9660 filesystem on any of the four discs. The only .SND file on disc is
AREAMAP.SND (276 bytes), which is the runtime area-music mapping table, not a
container of SEQ/TON banks. The game's music is fully covered by 86 standalone
.SEQ files with 89 .BIN tone banks; 5 SEQ files share a bank with another SEQ
under a different base name.

Usage:
    python tools/snd_split.py --scan  --disc1 <path>
    python tools/snd_split.py --extract --disc1 <path> [--disc2 <path>] ...
    python tools/snd_split.py --areamap --disc1 <path>
    python tools/snd_split.py --convert --output <dir>
"""

import os
import sys
import argparse
import json
import struct
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from common.iso9660 import ISO9660Reader

# ---------------------------------------------------------------------------
# Known SEQ -> BIN overrides for shared tone banks (LBA-verified on PDS USA)
# ---------------------------------------------------------------------------
SHARED_BANK_MAP = {
    "A3BGM1_1": "A3BGM",
    "A3BGM1_2": "A3BGM",
    "BOSS01_2":  "A3BOSS",
    "DRG_SE":    "DRG1SE",
    "TITLE":     "TITLEBGM",
}


def ru8(data, off):  return data[off]
def ru16(data, off): return struct.unpack_from('>H', data, off)[0]
def ru32(data, off): return struct.unpack_from('>I', data, off)[0]


# ---------------------------------------------------------------------------
# AREAMAP.SND parser
# ---------------------------------------------------------------------------

def parse_areamap_snd(data):
    """
    Parse AREAMAP.SND — the music area map command stream.

    The file is a sequence of variable-length area blocks, each terminated by
    0xFF.  Within each block the commands appear to be 7-byte DMA-style entries
    that the 68000 sound driver uses to copy SEQ/TON sub-banks out of SCSP RAM
    to the right channels.  Exact semantics are still under investigation;
    this function records the raw byte sequences per area for documentation.

    Returns: list of area records, each a dict with 'index' and 'raw' (bytes).
    """
    areas = []
    pos = 0
    area_idx = 0
    while pos < len(data):
        start = pos
        block = bytearray()
        while pos < len(data):
            b = data[pos]
            pos += 1
            block.append(b)
            if b == 0xFF:
                break
        if block:
            areas.append({
                'index': area_idx,
                'offset': start,
                'length': len(block),
                'raw': block.hex(),
            })
            area_idx += 1
    return areas


# ---------------------------------------------------------------------------
# SEQ / BIN catalogue builder
# ---------------------------------------------------------------------------

def build_catalogue(iso_path, disc_label):
    """
    Scan one disc image and return a catalogue dict of all SEQ/BIN music assets.
    """
    reader = ISO9660Reader(iso_path)
    files = reader.list_files()

    seq_files = {}
    bin_files = {}
    snd_entries = []

    for f in files:
        upper = f['name'].upper()
        base = upper.rsplit('.', 1)[0] if '.' in upper else upper
        if upper.endswith('.SEQ'):
            seq_files[base] = f
        elif upper.endswith('.BIN'):
            # Only BIN files that look like TON banks: small header with
            # mixer_off in the range 0x0008–0x2000
            data = reader.extract_file(f['lba'], min(f['size'], 8))
            if len(data) >= 8:
                mixer_off = ru16(data, 0)
                if 8 < mixer_off <= 0x2000 and f['size'] > 1024:
                    bin_files[base] = f
        elif upper == 'AREAMAP.SND':
            snd_data = reader.extract_file(f['lba'], f['size'])
            snd_entries = parse_areamap_snd(snd_data)

    # Build SEQ -> BIN pairs
    pairs = []
    for seq_base, seq_f in sorted(seq_files.items()):
        # Primary: exact name match
        ton_f = bin_files.get(seq_base)

        # Fallback: known shared bank overrides
        if ton_f is None:
            override_base = SHARED_BANK_MAP.get(seq_base)
            if override_base:
                ton_f = bin_files.get(override_base.upper())

        # Fallback: LBA proximity (nearest BIN within ±200 sectors)
        if ton_f is None:
            candidates = [
                (abs(b['lba'] - seq_f['lba']), b)
                for b in bin_files.values()
                if abs(b['lba'] - seq_f['lba']) <= 200
            ]
            candidates.sort(key=lambda x: x[0])
            if candidates:
                ton_f = candidates[0][1]

        pairs.append({
            'disc': disc_label,
            'seq': {
                'name': seq_f['name'],
                'lba':  seq_f['lba'],
                'size': seq_f['size'],
            },
            'ton': {
                'name': ton_f['name'],
                'lba':  ton_f['lba'],
                'size': ton_f['size'],
            } if ton_f else None,
            'shared_bank': seq_base in SHARED_BANK_MAP,
        })

    reader.close()

    return {
        'disc':    disc_label,
        'iso':     iso_path,
        'pairs':   pairs,
        'areamap': snd_entries,
    }


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_raw_files(catalogue, output_dir):
    """Extract raw SEQ and BIN files from the disc image."""
    iso_path = catalogue['iso']
    disc_label = catalogue['disc']

    disc_out = os.path.join(output_dir, disc_label, 'raw')
    os.makedirs(disc_out, exist_ok=True)

    reader = ISO9660Reader(iso_path)
    extracted = []

    # Write areamap JSON
    areamap_path = os.path.join(output_dir, disc_label, 'areamap.json')
    with open(areamap_path, 'w') as f:
        json.dump(catalogue['areamap'], f, indent=2)
    print(f"  Wrote {areamap_path}")

    seen_bins = set()  # avoid extracting the same shared BIN multiple times

    for pair in catalogue['pairs']:
        seq_info = pair['seq']
        ton_info = pair['ton']

        seq_out = os.path.join(disc_out, os.path.basename(seq_info['name']))
        if not os.path.exists(seq_out):
            data = reader.extract_file(seq_info['lba'], seq_info['size'])
            with open(seq_out, 'wb') as f:
                f.write(data)
            print(f"  SEQ {seq_info['name']} -> {seq_out}")

        if ton_info:
            ton_key = ton_info['name']
            if ton_key not in seen_bins:
                ton_out = os.path.join(disc_out, os.path.basename(ton_info['name']))
                if not os.path.exists(ton_out):
                    data = reader.extract_file(ton_info['lba'], ton_info['size'])
                    with open(ton_out, 'wb') as f:
                        f.write(data)
                    print(f"  BIN {ton_info['name']} -> {ton_out}")
                seen_bins.add(ton_key)

        extracted.append({
            'seq': seq_out,
            'ton': os.path.join(disc_out, os.path.basename(ton_info['name'])) if ton_info else None,
        })

    reader.close()
    return extracted


# ---------------------------------------------------------------------------
# Conversion (invoke existing tools)
# ---------------------------------------------------------------------------

def convert_extracted(catalogue, output_dir):
    """
    For each extracted pair, run ton_to_wav.py on the BIN and seq_to_midi.py
    on the SEQ.  Both tools must already be working (they are as of this
    writing).
    """
    disc_label = catalogue['disc']
    raw_dir = os.path.join(output_dir, disc_label, 'raw')
    wav_dir = os.path.join(output_dir, disc_label, 'wav')
    mid_dir = os.path.join(output_dir, disc_label, 'midi')
    os.makedirs(wav_dir, exist_ok=True)
    os.makedirs(mid_dir, exist_ok=True)

    tools_dir = os.path.dirname(os.path.abspath(__file__))
    ton_to_wav = os.path.join(tools_dir, 'ton_to_wav.py')
    seq_to_midi = os.path.join(tools_dir, 'seq_to_midi.py')

    seen_bins = set()

    for pair in catalogue['pairs']:
        seq_base = os.path.splitext(os.path.basename(pair['seq']['name']))[0]
        ton_info = pair['ton']

        # SEQ -> MIDI
        seq_in = os.path.join(raw_dir, os.path.basename(pair['seq']['name']))
        mid_out = os.path.join(mid_dir, seq_base + '.mid')
        if os.path.exists(seq_in) and not os.path.exists(mid_out):
            if os.path.exists(seq_to_midi):
                result = subprocess.run(
                    [sys.executable, seq_to_midi, '--input', seq_in, '--output', mid_out],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    print(f"  MIDI: {os.path.basename(mid_out)}")
                else:
                    print(f"  MIDI FAIL {seq_base}: {result.stderr.strip()[:120]}")
            else:
                print(f"  (seq_to_midi.py not found, skipping MIDI for {seq_base})")

        # BIN -> WAV samples (only once per shared bank)
        if ton_info:
            ton_base = os.path.splitext(os.path.basename(ton_info['name']))[0]
            if ton_base not in seen_bins:
                ton_in = os.path.join(raw_dir, os.path.basename(ton_info['name']))
                wav_out = os.path.join(wav_dir, ton_base)
                if os.path.exists(ton_in) and not os.path.exists(wav_out):
                    if os.path.exists(ton_to_wav):
                        result = subprocess.run(
                            [sys.executable, ton_to_wav, '--input', ton_in, '--output', wav_out],
                            capture_output=True, text=True
                        )
                        if result.returncode == 0:
                            print(f"  WAV samples: {ton_base}/")
                        else:
                            print(f"  WAV FAIL {ton_base}: {result.stderr.strip()[:120]}")
                    else:
                        print(f"  (ton_to_wav.py not found, skipping WAV for {ton_base})")
                seen_bins.add(ton_base)


# ---------------------------------------------------------------------------
# Report / summary
# ---------------------------------------------------------------------------

def print_catalogue_summary(catalogue):
    disc = catalogue['disc']
    pairs = catalogue['pairs']
    missing = [p for p in pairs if p['ton'] is None]
    shared = [p for p in pairs if p['shared_bank']]

    print(f"\n=== {disc} ===")
    print(f"  SEQ files:       {len(pairs)}")
    print(f"  Paired (BIN):    {len(pairs) - len(missing)}")
    print(f"  Shared banks:    {len(shared)}")
    print(f"  Missing BIN:     {len(missing)}")
    print(f"  AREAMAP areas:   {len(catalogue['areamap'])}")

    if missing:
        print("  Unpaired SEQ files:")
        for p in missing:
            print(f"    {p['seq']['name']}")

    if shared:
        print("  Shared bank SEQs:")
        for p in shared:
            print(f"    {p['seq']['name']} -> {p['ton']['name']}")


def print_full_catalogue(catalogue):
    print_catalogue_summary(catalogue)
    print()
    print("  All pairs:")
    for p in catalogue['pairs']:
        ton_name = p['ton']['name'] if p['ton'] else "MISSING"
        flag = " [shared]" if p['shared_bank'] else ""
        print(f"    {p['seq']['name']:25s} -> {ton_name}{flag}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='PDS SND Bundle Splitter & SEQ/BIN Catalogue Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--disc1', metavar='PATH', help='Disc 1 track 1 .bin path')
    parser.add_argument('--disc2', metavar='PATH', help='Disc 2 track 1 .bin path')
    parser.add_argument('--disc3', metavar='PATH', help='Disc 3 track 1 .bin path')
    parser.add_argument('--disc4', metavar='PATH', help='Disc 4 track 1 .bin path')
    parser.add_argument('--output', metavar='DIR',  default='output/snd_split',
                        help='Output directory (default: output/snd_split)')
    parser.add_argument('--scan',    action='store_true', help='Scan discs and print catalogue')
    parser.add_argument('--extract', action='store_true', help='Extract raw SEQ/BIN files')
    parser.add_argument('--convert', action='store_true', help='Convert SEQ->MIDI and BIN->WAV')
    parser.add_argument('--areamap', action='store_true', help='Parse and dump AREAMAP.SND')
    parser.add_argument('--full',    action='store_true', help='Print full pair list in scan')
    parser.add_argument('--save-catalogue', action='store_true',
                        help='Save catalogue JSON to output dir')

    args = parser.parse_args()

    disc_args = [
        ('disc1', args.disc1),
        ('disc2', args.disc2),
        ('disc3', args.disc3),
        ('disc4', args.disc4),
    ]

    discs_specified = [(label, path) for label, path in disc_args if path]
    if not discs_specified:
        parser.error("Specify at least one disc with --disc1, --disc2, --disc3, or --disc4.")

    os.makedirs(args.output, exist_ok=True)

    catalogues = []
    for label, path in discs_specified:
        if not os.path.exists(path):
            print(f"ERROR: disc image not found: {path}", file=sys.stderr)
            sys.exit(1)
        print(f"Scanning {label}: {path}")
        cat = build_catalogue(path, label)
        catalogues.append(cat)

        if args.save_catalogue:
            cat_path = os.path.join(args.output, f'catalogue_{label}.json')
            # Serialise — convert bytearray raw fields for JSON
            with open(cat_path, 'w') as f:
                json.dump(cat, f, indent=2, default=str)
            print(f"  Saved catalogue to {cat_path}")

    if args.scan:
        for cat in catalogues:
            if args.full:
                print_full_catalogue(cat)
            else:
                print_catalogue_summary(cat)

    if args.areamap:
        for cat in catalogues:
            print(f"\n=== AREAMAP.SND — {cat['disc']} ({len(cat['areamap'])} areas) ===")
            for area in cat['areamap']:
                raw_bytes = bytes.fromhex(area['raw'])
                hex_str = ' '.join(f'{b:02X}' for b in raw_bytes)
                print(f"  Area {area['index']:2d} @ 0x{area['offset']:04X} "
                      f"({area['length']:3d} bytes): {hex_str}")

    if args.extract:
        for cat in catalogues:
            print(f"\nExtracting {cat['disc']}...")
            extract_raw_files(cat, args.output)
        print("\nExtraction complete.")

    if args.convert:
        for cat in catalogues:
            print(f"\nConverting {cat['disc']}...")
            convert_extracted(cat, args.output)
        print("\nConversion complete.")

    if not any([args.scan, args.extract, args.convert, args.areamap]):
        print("No action specified. Use --scan, --extract, --convert, or --areamap.")
        print("Run with -h for help.")


if __name__ == '__main__':
    main()
