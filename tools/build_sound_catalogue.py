"""
Panzer Dragoon Saga — Sound Catalogue Builder

Parses SNDTEST.PRG from the disc to extract the game's official track names, then
pairs them with the extracted SEQ/BIN files from snd_split.py output to produce
output/sound_catalogue.json for use by the sound test browser UI.

SNDTEST.PRG is a hidden sound test overlay present on Disc 1. It contains 75
fixed-width (12-char) ASCII track names between the sentinel string 'COMMON' and
the hard terminator 'ERR_STOP'. These are the only official track labels in the game.

The SEQ_TO_SNDTEST mapping table below is structural metadata — it maps SEQ filenames
(read from the disc at runtime) to SNDTEST display name strings (read from SNDTEST.PRG
at runtime). No proprietary game audio or content is embedded in this script.

Usage:
    python tools/build_sound_catalogue.py --sndtest output/seq_extract/SNDTEST.PRG
                                          --raw-dir output/snd_split/disc1/raw
                                          --midi-dir output/snd_split/disc1/midi
                                          --wav-dir  output/snd_split/disc1/wav
                                          --output   output/sound_catalogue.json

    # Or with an ISO to extract SNDTEST.PRG on the fly:
    python tools/build_sound_catalogue.py --iso "ISOs/Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin"
                                          --raw-dir output/snd_split/disc1/raw
                                          ...
"""

import os
import re
import sys
import json
import argparse

# ---------------------------------------------------------------------------
# Shared-bank overrides (mirrors snd_split.py SHARED_BANK_MAP)
# SEQ base name -> BIN base name for the 5 cases where the names differ.
# ---------------------------------------------------------------------------
SHARED_BANK_MAP = {
    "A3BGM1_1": "A3BGM",
    "A3BGM1_2": "A3BGM",
    "BOSS01_2":  "A3BOSS",
    "DRG_SE":    "DRG1SE",
    "TITLE":     "TITLEBGM",
}

# ---------------------------------------------------------------------------
# SEQ filename stem -> SNDTEST display name
#
# Structural knowledge only — maps disc filenames to display name strings that
# are extracted at runtime from SNDTEST.PRG. No audio or game content here.
#
# Confidence legend:
#   "exact"    — unambiguous one-to-one match from filename conventions
#   "inferred" — best guess; verify via playback (TBD entries)
# ---------------------------------------------------------------------------
SEQ_TO_SNDTEST = {
    # A3 area
    "A3BGM1_1":  ("A3 1 1 (MAP)",  "exact"),
    "A3BGM1_2":  ("A3 1 2 (MAP)",  "exact"),
    "A3BGM2":    ("A3 2 (MAP)",    "exact"),
    "A3ZAKOSE":  ("A3 (ZAKO)",     "exact"),
    "A3SE":      ("A3 2 (ZAKO)",   "inferred"),  # SE = zako SFX variant; verify
    "A3BOSS":    ("A3 (MBOS)",     "inferred"),  # mini-boss or boss? verify

    # A5 area
    "A5BGM":     ("A5 (MAP)",      "exact"),
    "A5ZAKO":    ("A5 (ZAKO)",     "exact"),
    "A5BOSBGM":  ("A5 (MBOS)",     "inferred"),  # BOSBGM = boss BGM; MBOS or BOSS?
    "A5BOSS":    ("A5 (BOSS)",     "inferred"),
    "A5SE":      ("A5 (ZAKO)",     "inferred"),  # SE variant; may duplicate A5ZAKO slot

    # A7 area
    "A7BGM":     ("A7 (MAP)",      "exact"),
    "A7ZAKO":    ("A7 (ZAKO)",     "exact"),
    "A7MB":      ("A7 (MBOS)",     "exact"),     # MB = mini-boss
    "A7SE":      ("A7 (ZAKO)",     "inferred"),

    # B areas — note B1 files not present on disc (Disc 1 only covers visited areas)
    "B2BGM1":    ("B2 1 (MAP)",    "exact"),
    "B2BGM2":    ("B2 2 (MAP)",    "exact"),
    "B2BOS_SE":  ("B2 (BOSS)",     "inferred"),
    "B2SE":      ("B2 (MBOS)",     "inferred"),

    "B5BGM":     ("B5 1 (MAP)",    "inferred"),  # only one B5 BGM on disc
    "B5MB":      ("B5 (MBOS)",     "exact"),
    "B5SE":      ("B5 (ZAKO)",     "inferred"),

    "B6BGM":     ("B6 (MAP)",      "exact"),
    "B6ZAKOSE":  ("B6 (ZAKO)",     "exact"),
    "B6BOSSE":   ("B6 (BOSS)",     "inferred"),
    "B6SE":      ("B6 (MBOS)",     "inferred"),

    # C areas
    "C2BGM":     ("C2 (MAP)",      "exact"),
    "C2ZAKOSE":  ("C2 (ZAKO)",     "exact"),
    "C2MBSE":    ("C2 (MBOS)",     "exact"),     # MBSE = mini-boss SE
    "C2BOS_SE":  ("C2 (BOSS)",     "exact"),

    "C4BGM":     ("C4 (MAP)",      "exact"),
    "C4SE":      ("C4 (ZAKO)",     "inferred"),
    "C4MB_SE":   ("C4 (MBOS)",     "exact"),

    "C8BGM":     ("C8 (MAP)",      "exact"),
    "C7SE":      ("C8 (ZAKO)",     "inferred"),  # C7 SFX used in C8 area?
    "C8BOS_SE":  ("C8 (BOSS)",     "exact"),

    # D areas
    "D2BGM":     ("D2 (MAP)",      "exact"),
    "D2BOS_SE":  ("D2 (BOSS)",     "exact"),
    "D2SE":      ("D2 (MAP)",      "inferred"),  # may overlap; verify
    "D2MBSE":    ("D2 (MAP)",      "inferred"),

    "D3BGM":     ("D3 (MAP)",      "exact"),

    "D4BGM":     ("D4 (MAP)",      "exact"),
    "D4MB_SE":   ("D4 (MBOS)",     "exact"),

    "D5BGM":     ("D5 (MAP)",      "exact"),

    # Town and named location tracks
    "AD_SE":     ("AD",            "exact"),
    "HANU_SE":   ("HANU",          "exact"),
    "RUINSE":    ("RUIN",          "exact"),
    "EXCA_SE":   ("EXCA",          "exact"),
    "TOWNBGM":   ("TOWN",          "exact"),
    "PAETBGM":   ("PAET",          "exact"),
    "CARABGM":   ("CARAVAN",       "exact"),
    "CAMPBGM":   ("CAMP",          "exact"),
    "SEEBGM":    ("SEEKER",        "exact"),

    # Event tracks
    "E14SE":     ("EVENT 14",      "exact"),
    "E22SE":     ("EVENT 22",      "exact"),
    "E74SE":     ("EVENT 74",      "exact"),
    "E78BGM":    ("EVENT 78",      "exact"),
    "E78SE":     ("EVENT 78",      "inferred"),  # SE variant of E78BGM?
    "E128SE":    ("EVENT 128",     "exact"),
    # EVENT 06, EVENT 11: no obvious file match — TBD

    # Special tracks
    "TITLE":     ("TITLE",         "exact"),
    "DRG_SE":    ("DROGON 00",     "inferred"),  # DROGON 08 TBD — same file?
    "EDGE_SE":   ("EDGE",          "inferred"),  # EDGE2 TBD — same file?
}

# Category groupings for the UI (SNDTEST display name prefix -> category)
CATEGORY_ORDER = [
    ("Field Areas",   ["A3", "A5", "A7", "B1", "B2", "B3", "B5", "B6",
                       "C2", "C4", "C5", "C8", "D2", "D3", "D4", "D5"]),
    ("Towns & Events",["AD", "HANU", "RUIN", "EXCA", "TOWN", "PAET",
                       "CARAVAN", "CAMP", "SEEKER",
                       "EVENT 06", "EVENT 11", "EVENT 14", "EVENT 22",
                       "EVENT 74", "EVENT 78", "EVENT 128"]),
    ("Special",       ["TITLE", "DROGON 00", "DROGON 08", "EDGE", "EDGE2"]),
]


# ---------------------------------------------------------------------------
# SNDTEST.PRG parser
# ---------------------------------------------------------------------------

def parse_sndtest_prg(data):
    """
    Extract the ordered list of track names from SNDTEST.PRG binary data.

    The names are null/space-padded 12-byte ASCII strings stored sequentially
    after the sentinel string 'COMMON      ' and terminated by 'ERR_STOP'.
    We scan for all printable ASCII runs >=4 chars, find COMMON, then collect
    until ERR_STOP.

    Returns: list of str (stripped, in order)
    """
    strings = re.findall(b'[\x20-\x7E]{4,}', data)
    names = []
    started = False
    for raw in strings:
        s = raw.decode('ascii', errors='ignore').strip()
        if not s:
            continue
        if s == 'COMMON':
            started = True
            continue
        if not started:
            continue
        if s == 'ERR_STOP':
            break
        # Skip internal control tokens that may appear before the names block ends
        if s in ('NULL', 'PAUSE', 'START', 'HEADER', 'PLAY'):
            continue
        names.append(s)
    return names


# ---------------------------------------------------------------------------
# SEQ/BIN pair discovery from raw output directory
# ---------------------------------------------------------------------------

def discover_pairs(raw_dir):
    """
    Discover SEQ/BIN pairs from the raw extraction directory produced by snd_split.py.
    Returns a dict: seq_stem -> {'seq': filename, 'bin': filename or None, 'shared_bank': bool}
    """
    if not os.path.isdir(raw_dir):
        raise FileNotFoundError(f"Raw directory not found: {raw_dir}")

    files = os.listdir(raw_dir)
    seq_stems = {}
    bin_names = set()

    for fname in files:
        stem, ext = os.path.splitext(fname.upper())
        if ext == '.SEQ':
            seq_stems[stem] = fname
        elif ext == '.BIN':
            bin_names.add(stem)

    pairs = {}
    for stem, seq_fname in sorted(seq_stems.items()):
        # Primary: exact match
        bin_stem = stem if stem in bin_names else None

        # Fallback: shared bank override
        if bin_stem is None:
            override = SHARED_BANK_MAP.get(stem)
            if override and override.upper() in bin_names:
                bin_stem = override.upper()

        bin_fname = (bin_stem + '.BIN') if bin_stem else None
        # Find actual case-preserved filename
        if bin_fname:
            for f in files:
                if f.upper() == bin_fname:
                    bin_fname = f
                    break

        pairs[stem] = {
            'seq': seq_fname,
            'bin': bin_fname,
            'shared_bank': stem in SHARED_BANK_MAP,
        }

    return pairs


# ---------------------------------------------------------------------------
# Catalogue builder
# ---------------------------------------------------------------------------

def build_catalogue(sndtest_names, pairs, midi_dir, wav_dir):
    """
    Combine SNDTEST names with discovered SEQ/BIN pairs.

    Returns dict with:
      tracks        — named tracks (SNDTEST name + SEQ file)
      extra_tracks  — SEQ files with no SNDTEST name
      unmatched_names — SNDTEST names with no SEQ match on disc
    """
    used_stems = set()
    tracks = []
    unmatched_names = []

    for name in sndtest_names:
        # Find a SEQ stem that maps to this SNDTEST name
        matched_stem = None
        confidence = "unknown"
        for stem, (mapped_name, conf) in SEQ_TO_SNDTEST.items():
            if mapped_name == name and stem in pairs:
                # Prefer the first match; flag duplicates as inferred
                if matched_stem is None:
                    matched_stem = stem
                    confidence = conf
                # else: multiple SEQs map to same name (e.g. two ZAKO tracks) — keep first

        if matched_stem is None:
            unmatched_names.append(name)
            continue

        used_stems.add(matched_stem)
        pair = pairs[matched_stem]
        bin_stem = os.path.splitext(pair['bin'])[0].upper() if pair['bin'] else None

        # Determine category
        category = "Special"
        for cat_name, prefixes in CATEGORY_ORDER:
            if any(name.startswith(p) for p in prefixes):
                category = cat_name
                break

        tracks.append({
            "sndtest_name": name,
            "seq":          pair['seq'],
            "bin":          pair['bin'],
            "shared_bank":  pair['shared_bank'],
            "midi":         _find_file(midi_dir, matched_stem + '.mid'),
            "wav_dir":      _find_wav_dir(wav_dir, bin_stem) if bin_stem else None,
            "confidence":   confidence,
            "category":     category,
        })

    # Extra tracks: SEQ files not mapped to any SNDTEST name
    extra_tracks = []
    for stem, pair in sorted(pairs.items()):
        if stem in used_stems:
            continue
        bin_stem = os.path.splitext(pair['bin'])[0].upper() if pair['bin'] else None
        extra_tracks.append({
            "sndtest_name": None,
            "seq":          pair['seq'],
            "bin":          pair['bin'],
            "shared_bank":  pair['shared_bank'],
            "midi":         _find_file(midi_dir, stem + '.mid'),
            "wav_dir":      _find_wav_dir(wav_dir, bin_stem) if bin_stem else None,
            "confidence":   "unknown",
            "category":     "Extra Tracks",
        })

    return {
        "tracks":           tracks,
        "extra_tracks":     extra_tracks,
        "unmatched_names":  unmatched_names,
        "stats": {
            "sndtest_total":    len(sndtest_names),
            "named_matched":    len(tracks),
            "named_unmatched":  len(unmatched_names),
            "extra_seq_files":  len(extra_tracks),
            "total_seq_files":  len(pairs),
        }
    }


def _find_file(directory, filename):
    """Return relative path if file exists, else None."""
    if not directory:
        return None
    path = os.path.join(directory, filename)
    return path if os.path.exists(path) else None


def _find_wav_dir(wav_root, bin_stem):
    """Return wav subdirectory path if it exists, else None."""
    if not wav_root or not bin_stem:
        return None
    path = os.path.join(wav_root, bin_stem)
    return path if os.path.isdir(path) else None


# ---------------------------------------------------------------------------
# Optional: extract SNDTEST.PRG from an ISO image
# ---------------------------------------------------------------------------

def extract_sndtest_from_iso(iso_path):
    """
    Extract SNDTEST.PRG data directly from a disc image.
    Requires tools/common/iso9660.py to be importable.
    """
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, tools_dir)
    try:
        from common.iso9660 import ISO9660Reader, read_sector
    except ImportError:
        raise ImportError("Cannot import common.iso9660 — run from the repo root or tools/ dir")

    reader = ISO9660Reader(iso_path)
    files = reader.list_files()
    sndtest = next((f for f in files if f['name'].upper() == 'SNDTEST.PRG'), None)
    if sndtest is None:
        reader.close()
        raise FileNotFoundError("SNDTEST.PRG not found in ISO filesystem")

    num_sectors = (sndtest['size'] + 2047) // 2048
    data = b''
    for i in range(num_sectors):
        data += read_sector(reader.f, sndtest['lba'] + i)
    reader.close()
    return data[:sndtest['size']]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='PDS Sound Catalogue Builder — pairs SNDTEST.PRG names with extracted SEQ files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument('--sndtest', metavar='PATH',
                     help='Path to extracted SNDTEST.PRG file')
    src.add_argument('--iso', metavar='PATH',
                     help='Disc image to extract SNDTEST.PRG from directly')

    parser.add_argument('--raw-dir',  metavar='DIR', default='output/snd_split/disc1/raw',
                        help='Directory of extracted SEQ/BIN files (default: output/snd_split/disc1/raw)')
    parser.add_argument('--midi-dir', metavar='DIR', default='output/snd_split/disc1/midi',
                        help='Directory of converted MIDI files (default: output/snd_split/disc1/midi)')
    parser.add_argument('--wav-dir',  metavar='DIR', default='output/snd_split/disc1/wav',
                        help='Directory of WAV sample banks (default: output/snd_split/disc1/wav)')
    parser.add_argument('--output',   metavar='PATH', default='output/sound_catalogue.json',
                        help='Output JSON path (default: output/sound_catalogue.json)')
    parser.add_argument('--verbose',  action='store_true',
                        help='Print detailed match results')

    args = parser.parse_args()

    # --- Load SNDTEST.PRG ---
    if args.sndtest:
        if not os.path.exists(args.sndtest):
            print(f"ERROR: SNDTEST.PRG not found: {args.sndtest}", file=sys.stderr)
            sys.exit(1)
        with open(args.sndtest, 'rb') as f:
            sndtest_data = f.read()
    else:
        print(f"Extracting SNDTEST.PRG from ISO: {args.iso}")
        sndtest_data = extract_sndtest_from_iso(args.iso)
        print(f"  Extracted {len(sndtest_data)} bytes")

    # --- Parse names ---
    sndtest_names = parse_sndtest_prg(sndtest_data)
    print(f"SNDTEST track names extracted: {len(sndtest_names)}")

    # --- Discover SEQ/BIN pairs ---
    pairs = discover_pairs(args.raw_dir)
    print(f"SEQ files found in raw dir:    {len(pairs)}")

    # --- Build catalogue ---
    catalogue = build_catalogue(sndtest_names, pairs, args.midi_dir, args.wav_dir)

    stats = catalogue['stats']
    print(f"\nResults:")
    print(f"  Named (SNDTEST matched): {stats['named_matched']}")
    print(f"  SNDTEST unmatched:       {stats['named_unmatched']}")
    print(f"  Extra SEQ files:         {stats['extra_seq_files']}")
    print(f"  Total SEQ files:         {stats['total_seq_files']}")

    if catalogue['unmatched_names']:
        print(f"\nSNDTEST names with no SEQ match:")
        for n in catalogue['unmatched_names']:
            print(f"  {n!r}")

    if args.verbose:
        print(f"\nNamed tracks:")
        for t in catalogue['tracks']:
            flag = f" [{t['confidence']}]" if t['confidence'] != 'exact' else ""
            print(f"  {t['sndtest_name']:20s}  ->  {t['seq']}{flag}")
        print(f"\nExtra tracks (not in sound test):")
        for t in catalogue['extra_tracks']:
            print(f"  {t['seq']}")

    # --- Write output ---
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(catalogue, f, indent=2, default=str)
    print(f"\nCatalogue written to: {args.output}")


if __name__ == '__main__':
    main()
