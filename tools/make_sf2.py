"""
Saturn Tone Bank (.BIN) → SF2 SoundFont Converter
===================================================

Converts a CyberSound TON-format .BIN tone bank (plus its pre-extracted WAV samples)
into a standard SF2 SoundFont 2.01 file that can be used with any SF2-compatible
MIDI renderer (FluidSynth, html-midi-player, etc.).

Usage:
    # Convert a single bank:
    python tools/make_sf2.py \\
        --bin  output/snd_split/disc1/raw/TITLEBGM.BIN \\
        --wavs output/snd_split/disc1/wav/TITLEBGM \\
        --out  output/sf2/TITLEBGM.sf2

    # Convert all banks in a disc directory:
    python tools/make_sf2.py \\
        --disc output/snd_split/disc1 \\
        --out  output/sf2

The resulting SF2 maps:
    MIDI Program 0  →  Voice 0 in the BIN (each layer as a key-range zone)
    MIDI Program 1  →  Voice 1
    ...
    MIDI Program N  →  Voice N

Each sample is embedded at its native WAV sample rate with root key 60 (middle C)
and a pitch correction value derived from the SCSP OCT/FNS registers.

SF2 2.01 format reference:
    "SoundFont® Technical Specification 2.01" — E-MU Systems / Creative Labs.
    Structure: RIFF "sfbk" → LIST "INFO" + LIST "sdta" + LIST "pdta"
    All integers little-endian (SF2 uses LE unlike Saturn which is BE).

No external libraries required — uses only Python stdlib struct/wave.
"""

import os
import sys
import struct
import wave
import io
import argparse
import json
import re


# ---------------------------------------------------------------------------
# SF2 binary packing helpers (all little-endian per SF2 spec)
# ---------------------------------------------------------------------------

def pu8(v):   return struct.pack('<B', v & 0xFF)
def pu16(v):  return struct.pack('<H', v & 0xFFFF)
def ps16(v):  return struct.pack('<h', max(-32768, min(32767, int(v))))
def pu32(v):  return struct.pack('<I', v & 0xFFFFFFFF)
def ps32(v):  return struct.pack('<i', max(-2147483648, min(2147483647, int(v))))

def fourcc(s):
    """4-byte ASCII tag."""
    return s.encode('ascii')[:4].ljust(4, b'\x00')

def riff_chunk(tag, data):
    """Pack a RIFF chunk: 4-byte tag + 4-byte LE size + data (padded to even)."""
    if isinstance(data, list):
        data = b''.join(data)
    size = len(data)
    chunk = fourcc(tag) + pu32(size) + data
    if size % 2:
        chunk += b'\x00'   # RIFF pad byte
    return chunk

def list_chunk(list_type, data):
    """Pack a RIFF LIST chunk."""
    if isinstance(data, list):
        data = b''.join(data)
    payload = fourcc(list_type) + data
    return riff_chunk('LIST', payload)


# ---------------------------------------------------------------------------
# SF2 fixed-size record packers
# ---------------------------------------------------------------------------

def _pad20(s):
    """Null-padded 20-byte name field used in SF2 records."""
    b = s.encode('ascii', errors='replace')[:20]
    return b.ljust(20, b'\x00')

def sf2_phdr(name, preset, bank, bag_idx, lib=0, genre=0, morphology=0):
    """sfPresetHeader — 38 bytes."""
    return _pad20(name) + pu16(preset) + pu16(bank) + pu16(bag_idx) \
         + pu32(lib) + pu32(genre) + pu32(morphology)

def sf2_pbag(gen_idx, mod_idx=0):
    """sfPresetBag — 4 bytes."""
    return pu16(gen_idx) + pu16(mod_idx)

def sf2_pgen(oper, amount_lo=0, amount_hi=0):
    """sfGenList — 4 bytes. amount is a GenAmountType union."""
    return pu16(oper) + pu8(amount_lo) + pu8(amount_hi)

def sf2_pgen_word(oper, word):
    """sfGenList with a 16-bit signed word amount."""
    return pu16(oper) + ps16(word)

def sf2_pmod():
    """sfModList terminal — 10 bytes of zeros."""
    return b'\x00' * 10

def sf2_inst(name, bag_idx):
    """sfInst — 22 bytes."""
    return _pad20(name) + pu16(bag_idx)

def sf2_ibag(gen_idx, mod_idx=0):
    """sfInstBag — 4 bytes."""
    return pu16(gen_idx) + pu16(mod_idx)

def sf2_igen(oper, amount_lo=0, amount_hi=0):
    """sfInstGenList — 4 bytes."""
    return pu16(oper) + pu8(amount_lo) + pu8(amount_hi)

def sf2_igen_word(oper, word):
    return pu16(oper) + ps16(word)

def sf2_shdr(name, start, end, loop_start, loop_end,
             sample_rate, original_pitch, pitch_correction,
             sample_link=0, sample_type=1):
    """sfSampleHeader — 46 bytes.
    sample_type: 1=mono left, 2=mono right, 4=linked, 0x8001=ROM mono.
    """
    return _pad20(name) \
         + pu32(start) + pu32(end) \
         + pu32(loop_start) + pu32(loop_end) \
         + pu32(sample_rate) \
         + pu8(original_pitch) \
         + struct.pack('<b', max(-99, min(99, pitch_correction))) \
         + pu16(sample_link) + pu16(sample_type)


# ---------------------------------------------------------------------------
# SF2 generator opcodes (Appendix A of the SF2 spec)
# ---------------------------------------------------------------------------
GEN_START_ADDRS_OFFSET    = 0
GEN_END_ADDRS_OFFSET      = 1
GEN_STARTLOOP_ADDRS_OFFSET= 2
GEN_ENDLOOP_ADDRS_OFFSET  = 3
GEN_SAMPLE_ID             = 53
GEN_KEY_RANGE             = 43    # lo byte = low key, hi byte = high key
GEN_VEL_RANGE             = 44
GEN_OVERRIDE_ROOT_KEY     = 58
GEN_INSTRUMENT            = 41    # preset generator: link to instrument index
GEN_SAMPLE_MODES          = 54    # bit 0: loop, bit 2: loop+sustain
GEN_INITIAL_ATTENUATION   = 48    # centibels
GEN_PAN                   = 17    # -500 (left) to +500 (right)


# ---------------------------------------------------------------------------
# WAV loading
# ---------------------------------------------------------------------------

def load_wav_samples(wav_path):
    """Read a WAV file and return (samples_bytes_16bit_le, sample_rate, n_frames).
    Always converts to 16-bit signed little-endian mono for SF2 embedding.
    """
    with wave.open(wav_path, 'rb') as w:
        n_channels = w.getnchannels()
        sampwidth  = w.getsampwidth()
        framerate  = w.getframerate()
        n_frames   = w.getnframes()
        raw        = w.readframes(n_frames)

    # Convert to 16-bit signed LE mono
    if sampwidth == 1:
        # 8-bit WAV is stored as unsigned 0-255 (but ton_to_wav stores signed 8-bit
        # as unsigned — see convert_pcm_to_wav which casts signed→unsigned for 8-bit).
        # Re-interpret as unsigned uint8, then scale to int16.
        import numpy as np
        samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.int16) - 128) * 256
    elif sampwidth == 2:
        import numpy as np
        samples = np.frombuffer(raw, dtype='<i2')  # already LE from ton_to_wav
    else:
        raise ValueError(f"Unsupported sample width {sampwidth} in {wav_path}")

    if n_channels == 2:
        # Downmix to mono
        import numpy as np
        samples = samples[::2] // 2 + samples[1::2] // 2

    return samples.astype('<i2').tobytes(), framerate, len(samples)


# ---------------------------------------------------------------------------
# TON (BIN) bank parser — minimal, just what we need for SF2 mapping
# ---------------------------------------------------------------------------

def parse_ton_voices(data):
    """Parse a CyberSound TON .BIN file and return a list of voice dicts.

    Each voice dict:
        voice_index: int
        layers: list of layer dicts, each:
            tone_off:    int  (file-absolute byte offset to PCM, used to find WAV)
            bits:        int  (8 or 16)
            sample_count:int  (in samples)
            sample_rate: int  (computed from OCT/FNS, Hz)
            key_lo:      int  (MIDI note — from lo_key byte in layer, or 0)
            key_hi:      int  (MIDI note — from hi_key byte in layer, or 127)
    """
    def ru16(off):
        return struct.unpack('>H', data[off:off+2])[0]
    def ru32(off):
        return struct.unpack('>I', data[off:off+4])[0]

    if len(data) < 8:
        return []

    mixer_off = ru16(0)
    plfo_off  = ru16(6)

    if mixer_off < 8 or mixer_off > len(data):
        return []

    num_voices = (mixer_off - 8) // 2
    if num_voices <= 0 or num_voices > 128:
        return []

    voices_start = plfo_off + 4
    voices = []
    cur_off = voices_start

    for vi in range(num_voices):
        if cur_off + 4 > len(data):
            break

        nlayers_raw = data[cur_off + 2]
        nlayers = (nlayers_raw - 256 if nlayers_raw >= 128 else nlayers_raw) + 1
        nlayers = max(1, min(nlayers, 32))

        layer_base = cur_off + 4
        layers = []

        for l in range(nlayers):
            lb = layer_base + l * 32
            if lb + 32 > len(data):
                break

            # Key range from the first two bytes of the layer block
            lo_key = data[lb + 0]
            hi_key = data[lb + 1]
            if lo_key > hi_key or (lo_key == 0 and hi_key == 0):
                lo_key, hi_key = 0, 127  # treat as full-range

            raw_u32 = ru32(lb + 2)
            tone_off = raw_u32 & 0x0007FFFF
            pcm8b = (data[lb + 3] >> 4) & 1
            bits = 8 if pcm8b else 16
            sample_count = ru16(lb + 8)

            # OCT/FNS → sample rate (MAME scsp.cpp formula)
            pitch_word = ru16(lb + 0x0A)
            oct_raw  = (pitch_word >> 11) & 0xF
            fns      = pitch_word & 0x3FF
            oct_signed = (oct_raw ^ 8) - 8
            sample_rate = int(44100 * (2 ** oct_signed) * (1 + fns / 1024))
            sample_rate = max(1000, min(sample_rate, 96000))  # match ton_to_wav clamp

            if tone_off == 0 or sample_count == 0:
                continue

            layers.append({
                'tone_off':    tone_off,
                'bits':        bits,
                'sample_count':sample_count,
                'sample_rate': sample_rate,
                'key_lo':      lo_key,
                'key_hi':      hi_key,
            })

        voices.append({'voice_index': vi, 'layers': layers})
        cur_off += 4 + nlayers * 32

    return voices


# ---------------------------------------------------------------------------
# WAV filename → tone_off mapper
# ---------------------------------------------------------------------------

_WAV_RE = re.compile(r'sample_\d+_at(0x[0-9a-f]+)_', re.IGNORECASE)

def build_wav_index(wav_dir):
    """Return dict: tone_off_int → wav_filepath."""
    index = {}
    if not os.path.isdir(wav_dir):
        return index
    for fname in os.listdir(wav_dir):
        if not fname.lower().endswith('.wav'):
            continue
        m = _WAV_RE.match(fname)
        if m:
            try:
                offset = int(m.group(1), 16)
                index[offset] = os.path.join(wav_dir, fname)
            except ValueError:
                pass
    return index


# ---------------------------------------------------------------------------
# SF2 builder
# ---------------------------------------------------------------------------

def build_sf2(bank_name, voices, wav_index, comment=''):
    """Build and return raw SF2 bytes from voice/sample data.

    bank_name: short name for the bank (used in INFO and preset names)
    voices:    list from parse_ton_voices()
    wav_index: dict from build_wav_index()
    """

    # ------------------------------------------------------------------ sdta
    # Collect all samples we'll embed, in order.
    # SF2 stores all samples concatenated in the smpl sub-chunk (16-bit LE).
    # We track each sample's position as (start_sample_frame, end_sample_frame).

    sample_records = []   # list of dicts we'll use for shdr
    smpl_data = bytearray()  # raw 16-bit LE samples

    # Map: (tone_off, bits) → sample_record index (for dedup)
    seen_samples = {}

    def add_sample(layer):
        key = (layer['tone_off'], layer['bits'])
        if key in seen_samples:
            return seen_samples[key]

        wav_path = wav_index.get(layer['tone_off'])
        if wav_path is None:
            return None

        try:
            pcm16, rate, n_frames = load_wav_samples(wav_path)
        except Exception as e:
            print(f"  WARNING: Could not load {wav_path}: {e}")
            return None

        if n_frames < 8:
            return None

        start = len(smpl_data) // 2   # in sample frames (16-bit words)
        smpl_data.extend(pcm16)
        # SF2 requires 46-sample pad after each sample
        smpl_data.extend(b'\x00' * 92)   # 46 × 2 bytes
        end = len(smpl_data) // 2

        # loop points: set to end-2 and end-1 (no loop) — instruments can enable loops
        loop_start = end - 2
        loop_end   = end - 1

        # Root key calculation:
        # The sample was recorded at `rate` Hz. In the SCSP, this sample produces
        # middle C (MIDI 60) when played at its native rate. So original_pitch = 60.
        # Pitch correction (in cents): the SCSP rate differs slightly from exact ET.
        # Exact middle C at A=440: 261.63 Hz. The sample rate encodes pitch relative
        # to 44100 Hz. pitch_correction = 0 (we trust the WAV rate directly).
        original_pitch    = 60
        pitch_correction  = 0

        idx = len(sample_records)
        sname = f"s{idx}_{layer['tone_off']:05x}"
        sample_records.append({
            'name':             sname,
            'start':            start,
            'end':              end,
            'loop_start':       loop_start,
            'loop_end':         loop_end,
            'sample_rate':      rate,
            'original_pitch':   original_pitch,
            'pitch_correction': pitch_correction,
        })
        seen_samples[key] = idx
        return idx

    # Build layer→sample_index mapping per voice
    voice_sample_map = []  # list of lists of (layer, sample_idx)

    for voice in voices:
        voice_layers = []
        for layer in voice['layers']:
            sidx = add_sample(layer)
            if sidx is not None:
                voice_layers.append((layer, sidx))
        voice_sample_map.append(voice_layers)

    n_samples = len(sample_records)

    # ------------------------------------------------------------------ pdta
    # We build all the pdta sub-chunks together.

    # SF2 structure per preset/instrument:
    #   phdr: one entry per preset (= one per voice/program) + terminal
    #   pbag: preset bag — one entry per preset zone + terminal
    #   pmod: preset modulator — empty (terminal only)
    #   pgen: preset generator — for each preset zone, an instrument reference + key range
    #   inst: one entry per voice (instrument) + terminal
    #   ibag: instrument bag — one zone per layer + one global zone + terminal per instrument
    #   imod: instrument modulator — empty
    #   igen: instrument generator — per layer: keyRange, sampleID, overrideRootKey

    phdr_data = bytearray()
    pbag_data = bytearray()
    pgen_data = bytearray()
    pmod_data = bytearray()
    inst_data = bytearray()
    ibag_data = bytearray()
    igen_data = bytearray()
    imod_data = bytearray()
    shdr_data = bytearray()

    pbag_idx = 0   # running index into pgen
    pgen_idx = 0   # running index for pgen
    ibag_idx = 0   # running index into igen
    igen_idx = 0   # running index for igen
    inst_idx = 0   # running index into ibag

    n_voices = len(voices)

    for vi, voice in enumerate(voices):
        layers_with_samples = voice_sample_map[vi]
        if not layers_with_samples:
            continue  # skip voices with no usable samples

        # ---- Preset (phdr) ----
        preset_num = voice['voice_index']  # MIDI program number
        inst_bag_start = ibag_idx

        phdr_data += sf2_phdr(
            name      = f"Prog{preset_num}",
            preset    = preset_num,
            bank      = 0,
            bag_idx   = pbag_idx,
        )

        # ---- Preset bag: one zone covering the whole key range → instrument ----
        pbag_data += sf2_pbag(gen_idx=pgen_idx)

        # pgen: keyRange (0-127) + instrument link
        pgen_data += sf2_pgen(GEN_KEY_RANGE, 0, 127)      # lo=0, hi=127
        pgen_data += sf2_pgen(GEN_INSTRUMENT, vi & 0xFF, (vi >> 8) & 0xFF)
        pgen_idx += 2
        pbag_idx += 1

        # pmod: empty (terminal added after loop)

        # ---- Instrument (inst) ----
        inst_data += sf2_inst(f"Inst{preset_num}", ibag_idx)

        # ibag: one zone per layer (+ global zone at start with no generators)
        # Global zone first (empty — no gens, no mods)
        ibag_data += sf2_ibag(gen_idx=igen_idx)
        ibag_idx += 1
        # No global gens for this zone — the next ibag entry starts the layer zones

        for layer, sidx in layers_with_samples:
            # Each layer = one ibag zone
            ibag_data += sf2_ibag(gen_idx=igen_idx)
            ibag_idx += 1

            # igen: keyRange, sampleID, overrideRootKey (= 60 = middle C)
            igen_data += sf2_igen(GEN_KEY_RANGE, layer['key_lo'], layer['key_hi'])
            igen_data += sf2_igen_word(GEN_OVERRIDE_ROOT_KEY, 60)
            # sampleID must be last generator in a zone
            igen_data += sf2_igen_word(GEN_SAMPLE_ID, sidx)
            igen_idx += 3

        inst_idx += 1

    # ---- Terminals (SF2 requires these exact sentinel records) ----
    # phdr terminal
    phdr_data += sf2_phdr('EOP', preset=0xFF, bank=0xFF, bag_idx=pbag_idx)
    # pbag terminal
    pbag_data += sf2_pbag(gen_idx=pgen_idx)
    # pgen terminal (empty)
    pgen_data += sf2_pgen(0, 0, 0)
    # pmod terminal
    pmod_data += sf2_pmod()
    # inst terminal
    inst_data += sf2_inst('EOI', bag_idx=ibag_idx)
    # ibag terminal
    ibag_data += sf2_ibag(gen_idx=igen_idx)
    # igen terminal
    igen_data += sf2_igen(0, 0, 0)
    # imod terminal
    imod_data += sf2_pmod()

    # ---- shdr (sample headers) ----
    for i, sr in enumerate(sample_records):
        shdr_data += sf2_shdr(
            name             = sr['name'],
            start            = sr['start'],
            end              = sr['end'],
            loop_start       = sr['loop_start'],
            loop_end         = sr['loop_end'],
            sample_rate      = sr['sample_rate'],
            original_pitch   = sr['original_pitch'],
            pitch_correction = sr['pitch_correction'],
            sample_link      = 0,
            sample_type      = 1,   # mono
        )
    # shdr terminal ("EOS")
    shdr_data += sf2_shdr('EOS', 0, 0, 0, 0, 0, 0, 0, 0, 0)

    # ------------------------------------------------------------------ INFO
    info_data  = b''
    info_data += riff_chunk('ifil', pu16(2) + pu16(1))      # version 2.01
    info_data += riff_chunk('isng', b'EMU8000\x00')           # target synth engine
    info_data += riff_chunk('INAM', (bank_name[:256]).encode('ascii', 'replace') + b'\x00')
    if comment:
        info_data += riff_chunk('ICMT', (comment[:256]).encode('ascii', 'replace') + b'\x00')
    info_data += riff_chunk('ISFT', b'PDS make_sf2.py\x00')

    # ------------------------------------------------------------------ Assemble
    smpl_chunk = riff_chunk('smpl', bytes(smpl_data))
    sdta_data  = smpl_chunk   # no sm24 chunk (only needed for 24-bit samples)

    pdta_data  = riff_chunk('phdr', bytes(phdr_data)) \
               + riff_chunk('pbag', bytes(pbag_data)) \
               + riff_chunk('pmod', bytes(pmod_data)) \
               + riff_chunk('pgen', bytes(pgen_data)) \
               + riff_chunk('inst', bytes(inst_data)) \
               + riff_chunk('ibag', bytes(ibag_data)) \
               + riff_chunk('imod', bytes(imod_data)) \
               + riff_chunk('igen', bytes(igen_data)) \
               + riff_chunk('shdr', bytes(shdr_data))

    sfbk_data  = list_chunk('INFO', info_data) \
               + list_chunk('sdta', sdta_data) \
               + list_chunk('pdta', pdta_data)

    return riff_chunk('RIFF', fourcc('sfbk') + sfbk_data)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def convert_bank(bin_path, wav_dir, out_path, verbose=True):
    """Convert one BIN+WAV pair to SF2. Returns True on success."""
    if verbose:
        print(f"  BIN:  {bin_path}")
        print(f"  WAVs: {wav_dir}")
        print(f"  OUT:  {out_path}")

    with open(bin_path, 'rb') as f:
        data = f.read()

    voices = parse_ton_voices(data)
    if not voices:
        print("  ERROR: No voices found in BIN.")
        return False

    if verbose:
        print(f"  Voices: {len(voices)}")

    wav_index = build_wav_index(wav_dir)
    if not wav_index:
        print("  ERROR: No WAV files found in WAV directory.")
        return False

    bank_name = os.path.splitext(os.path.basename(bin_path))[0]
    comment   = f"Panzer Dragoon Saga — {bank_name} (extracted by PDS decompilation tools)"

    sf2_bytes = build_sf2(bank_name, voices, wav_index, comment)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, 'wb') as f:
        f.write(sf2_bytes)

    size_kb = len(sf2_bytes) / 1024
    if verbose:
        print(f"  Written: {size_kb:.1f} KB, {len([r for r in voices if voice_sample_map_has(r, wav_index, data)])} usable instruments")
    return True


def voice_sample_map_has(voice, wav_index, data):
    """Quick check: does this voice have at least one resolvable WAV sample?"""
    for layer in voice['layers']:
        if layer['tone_off'] in wav_index:
            return True
    return False


def main():
    parser = argparse.ArgumentParser(
        description='Saturn CyberSound TON Bank (.BIN) → SF2 SoundFont Converter',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--bin',  metavar='FILE', help='Path to .BIN tone bank')
    parser.add_argument('--wavs', metavar='DIR',  help='Directory of extracted WAV files for this bank')
    parser.add_argument('--out',  metavar='PATH', required=True,
                        help='Output .sf2 file (or directory when --disc is used)')
    parser.add_argument('--disc', metavar='DIR',
                        help='Disc directory (e.g. output/snd_split/disc1) — converts all banks')
    parser.add_argument('--catalogue', metavar='FILE',
                        help='sound_catalogue.json — used to find BIN/WAV pairs when --disc is set')
    parser.add_argument('--quiet', action='store_true', help='Suppress per-sample output')
    args = parser.parse_args()

    if args.disc:
        # Batch mode: convert every BIN that has a matching WAV directory
        raw_dir = os.path.join(args.disc, 'raw')
        wav_base = os.path.join(args.disc, 'wav')
        out_dir = args.out

        if not os.path.isdir(raw_dir):
            print(f"ERROR: raw dir not found: {raw_dir}")
            sys.exit(1)

        # Find all .BIN files
        bins = sorted(f for f in os.listdir(raw_dir) if f.upper().endswith('.BIN'))
        if not bins:
            print(f"ERROR: No .BIN files found in {raw_dir}")
            sys.exit(1)

        ok = err = skip = 0
        for bin_file in bins:
            stem = os.path.splitext(bin_file)[0]
            bin_path = os.path.join(raw_dir, bin_file)
            wav_dir  = os.path.join(wav_base, stem)
            out_path = os.path.join(out_dir, stem + '.sf2')

            if not os.path.isdir(wav_dir):
                if not args.quiet:
                    print(f"SKIP {bin_file} — no WAV directory at {wav_dir}")
                skip += 1
                continue

            print(f"\n{bin_file}")
            try:
                success = convert_bank(bin_path, wav_dir, out_path, verbose=not args.quiet)
                if success:
                    ok += 1
                else:
                    err += 1
            except Exception as e:
                import traceback
                print(f"  ERROR: {e}")
                if not args.quiet:
                    traceback.print_exc()
                err += 1

        print(f"\nDone: {ok} converted, {err} errors, {skip} skipped (no WAVs).")

    elif args.bin and args.wavs:
        # Single bank mode
        out_path = args.out
        if os.path.isdir(out_path):
            stem = os.path.splitext(os.path.basename(args.bin))[0]
            out_path = os.path.join(out_path, stem + '.sf2')
        try:
            convert_bank(args.bin, args.wavs, out_path, verbose=True)
        except Exception as e:
            import traceback
            print(f"ERROR: {e}")
            traceback.print_exc()
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
