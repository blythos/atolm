"""
Saturn Tone Bank (.BIN) to WAV Extractor

Extracts PCM instrument samples from CyberSound TON-format banks (.BIN files paired
with .SEQ files on Panzer Dragoon Saga disc).

Format reference:
  - CyberSound TON format structure verified against tonext.py by kingshriek
    (part of the SSF/Saturn Sound Format toolchain, available via VGMToolbox).
  - SCSP hardware register layout from Yabause/Kronos source and MAME's scsp.cpp.
  - TONCNV by CyberWarriorX for independent cross-check of sample extraction logic.
  - All field positions confirmed against raw binary data from PDS USA Disc 1.
"""

import os
import struct
import argparse
import wave
import numpy as np

class TONParser:
    def __init__(self, data):
        self.data = data

    def _read_u16(self, offset):
        if offset + 2 > len(self.data): return 0
        return struct.unpack('>H', self.data[offset:offset+2])[0]

    def _read_u32(self, offset):
        if offset + 4 > len(self.data): return 0
        return struct.unpack('>I', self.data[offset:offset+4])[0]

    def convert_pcm_to_wav(self, pcm_data, output_path, rate, bits, channels, big_endian=True, signed=True):
        """Converts raw PCM data to WAV using logic from pcm_extract.py."""
        if bits == 16:
            dtype_str = '>' if big_endian else '<'
            dtype_str += 'i2' if signed else 'u2'
            # Multiples of 2
            pcm_data = pcm_data[:(len(pcm_data)//2)*2]
            if not pcm_data: return False
            samples = np.frombuffer(pcm_data, dtype=dtype_str)
            if signed:
                samples = samples.astype('<i2')
            else:
                samples = (samples.astype(np.int32) - 32768).astype('<i2')
        elif bits == 8:
            dtype_str = 'int8' if signed else 'uint8'
            samples = np.frombuffer(pcm_data, dtype=dtype_str)
            if signed:
                samples = (samples.astype(np.int16) + 128).astype(np.uint8)
        else:
            return False

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with wave.open(output_path, 'wb') as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(bits // 8)
            wav_file.setframerate(rate)
            wav_file.writeframes(samples.tobytes())
        return True

    def extract_heuristically(self, output_dir):
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # TON (CyberSound tone bank) file structure:
        #
        # Bytes 0-7: Header — four u16 big-endian section offsets:
        #   mixer_off = ru16(0)  → mixer section (one SCSP slot + padding)
        #   vl_off    = ru16(2)  → volume/level section
        #   peg_off   = ru16(4)  → pitch envelope generator section
        #   plfo_off  = ru16(6)  → pitch LFO section (always 4 bytes)
        #
        # Bytes 8..(mixer_off-1): Voice offset table
        #   num_voices = (mixer_off - 8) / 2
        #   Each entry: u16 byte offset to that voice's descriptor
        #
        # Mixer/VL/PEG/PLFO sections: structured data for playback, not needed here
        #
        # Voice descriptors: starting at plfo_off + 4, laid out sequentially
        #   Each voice: [4-byte header][nlayers × 32-byte layer blocks]
        #   header byte[2] = nlayers - 1 (signed)
        #
        # Each 32-byte layer block:
        #   +0x00: LSA low byte, LSA high byte (loop start, not needed)
        #   +0x02..+0x05: u32 big-endian
        #       bits[18:0] masked as 0x0007FFFF = tone_off (file-absolute byte offset to PCM data)
        #       byte[+0x03] bit 4 = PCM8B flag (1 = 8-bit, 0 = 16-bit)
        #   +0x06..+0x07: LEA (loop end address, not used — sample_count is authoritative)
        #   +0x08..+0x09: u16 = sample_count (in samples, not bytes)
        #   +0x0A..+0x1F: ADSR, LFO, panning, etc. (not needed for extraction)
        #
        # PCM data: embedded at the tone_off byte offsets within the file itself.
        # tone_off is a direct file-absolute byte offset — no separate pcm_start needed.
        # Sample rate: not reliably encoded; default 22050 Hz.

        if len(self.data) < 8:
            print("File too small to be a valid TON bank.")
            return

        mixer_off = self._read_u16(0)
        plfo_off  = self._read_u16(6)

        if mixer_off < 8 or mixer_off > len(self.data):
            print(f"Invalid mixer offset {hex(mixer_off)}, aborting.")
            return

        num_voices = (mixer_off - 8) // 2
        if num_voices <= 0 or num_voices > 512:
            print(f"Unreasonable voice count {num_voices}, aborting.")
            return

        voices_start = plfo_off + 4  # voice descriptors begin here
        print(f"TON: {num_voices} voices, voices_start={hex(voices_start)}")

        found_samples = []

        cur_off = voices_start
        for i in range(num_voices):
            if cur_off + 4 > len(self.data):
                break

            # header byte[2] = signed nlayers - 1
            nlayers_raw = self.data[cur_off + 2]
            nlayers = (nlayers_raw - 256 if nlayers_raw >= 128 else nlayers_raw) + 1
            nlayers = max(1, min(nlayers, 32))  # sanity clamp

            layer_base = cur_off + 4
            for l in range(nlayers):
                lb = layer_base + l * 32
                if lb + 32 > len(self.data):
                    break

                # tone_off: u32 at lb+2 masked to 19 bits = file-absolute byte offset to PCM
                raw_u32 = self._read_u32(lb + 2)
                tone_off = raw_u32 & 0x0007FFFF

                # PCM8B: bit 4 of the byte at lb+3 (high byte of the lower 16 of the u32)
                pcm8b = (self.data[lb + 3] >> 4) & 1
                bits = 8 if pcm8b else 16

                # sample_count: u16 at lb+8 (count in samples, not bytes)
                sample_count = self._read_u16(lb + 8)

                if tone_off == 0 or sample_count == 0:
                    continue  # unused/empty layer

                length_bytes = sample_count if pcm8b else sample_count * 2

                found_samples.append({
                    'tone_off': tone_off,
                    'count': sample_count,
                    'len': length_bytes,
                    'bits': bits,
                })

            cur_off += 4 + nlayers * 32

        # Deduplicate — multiple voices can reference the same PCM region
        unique_samples = []
        seen = set()
        for s in found_samples:
            key = (s['tone_off'], s['count'], s['bits'])
            if key not in seen:
                unique_samples.append(s)
                seen.add(key)

        unique_samples.sort(key=lambda x: x['tone_off'])
        print(f"Found {len(unique_samples)} unique samples")

        # Default sample rate: 22050 Hz (Saturn instrument samples are typically this rate).
        # The actual playback rate is determined at runtime by the sequencer via OCT/FNS
        # pitch adjustments, which are relative transpositions, not absolute sample rates.
        DEFAULT_RATE = 22050

        count = 0
        for s in unique_samples:
            file_off = s['tone_off']

            if file_off >= len(self.data) or s['len'] <= 0:
                continue

            # Clamp to physical file end
            length = min(s['len'], len(self.data) - file_off)
            if length < 16:
                continue  # skip micro-samples

            sample_data = self.data[file_off : file_off + length]

            bit_label = '8bit' if s['bits'] == 8 else '16bit'
            wav_name = f"sample_{count:03d}_at{hex(file_off)}_{bit_label}_{DEFAULT_RATE}hz.wav"
            wav_path = os.path.join(output_dir, wav_name)

            success = self.convert_pcm_to_wav(
                sample_data, wav_path,
                rate=DEFAULT_RATE, bits=s['bits'], channels=1,
                big_endian=True, signed=True
            )
            if success:
                count += 1

        print(f"Extracted {count} valid samples to {output_dir}")

def main():
    parser = argparse.ArgumentParser(description='Saturn Tone Bank (.BIN) to WAV Extractor')
    parser.add_argument('--input', type=str, required=True, help='Path to .BIN tone bank')
    parser.add_argument('--output', type=str, required=True, help='Output directory')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        return

    with open(args.input, 'rb') as f:
        data = f.read()
        
    parser = TONParser(data)
    parser.extract_heuristically(args.output)

if __name__ == "__main__":
    main()
