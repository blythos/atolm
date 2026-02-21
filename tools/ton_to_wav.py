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
            
        # 1) Detect PCM Start offset
        # The first word is distance in bytes to the first sample block? No, it's the size of the jump table in bytes!
        first_ptr = self._read_u16(0)
        num_entries = first_ptr // 2
        pointers = []
        for i in range(min(num_entries, 256)): # Safety cap
            ptr = self._read_u16(i * 2)
            if ptr != 0xFFFF and ptr < len(self.data):
                pointers.append(ptr)
        
        if not pointers:
            print("No valid instrument pointers found.")
            return

        pcm_start = ((max(pointers) + 128 + 0x3F) // 0x40) * 0x40
        print(f"Detected PCM start at {hex(pcm_start)}")

        found_samples = []
        
        # 2) Traverse SDDRVS jump table
        for ptr in pointers:
            if ptr + 4 > len(self.data) or ptr >= pcm_start:
                continue
            
            # The structure is: 4-byte header, followed by N * 32-byte layer definitions.
            # Header Word 1's high byte dictates (Number of Layers - 1).
            header_w1 = self._read_u16(ptr + 2)
            num_layers = (header_w1 >> 8) + 1
            
            block_offset = ptr + 4
            for layer in range(num_layers):
                if block_offset + 32 > len(self.data):
                    break
                
                word0 = self._read_u16(block_offset + 0)
                word1 = self._read_u16(block_offset + 2)
                word2 = self._read_u16(block_offset + 4)
                word3 = self._read_u16(block_offset + 6) # LSA
                word4 = self._read_u16(block_offset + 8) # LEA
                
                # Check bit 4 for Mode (0=16-bit PCM, 1=8-bit PCM)
                is_8bit = (word0 & 0x0010) != 0
                mode = 0 if is_8bit else 1
                bits = 8 if is_8bit else 16
                
                # SA is 20-bit: (Word 1 Low Byte & 0x03) << 16 | Word 2
                sa = ((word1 & 0x03) << 16) | word2
                
                # Length in bytes: LEA is strictly in words (1 word = 2 bytes) for both 8-bit and 16-bit.
                length_bytes = word4 * 2
                
                if length_bytes > 0:
                    found_samples.append({'sa': sa, 'len': length_bytes, 'bits': bits, 'mode': mode})
                
                block_offset += 32
        
        # Deduplicate identical sample references
        unique_samples = []
        seen = set()
        for s in found_samples:
            key = (s['sa'], s['len'], s['bits'])
            if key not in seen:
                unique_samples.append(s)
                seen.add(key)
        
        unique_samples.sort(key=lambda x: x['sa'])
        
        count = 0
        for s in unique_samples:
            sa = s['sa']
            length = s['len']
            bits = s['bits']
            mode = s['mode']
            
            file_off = pcm_start + sa
            
            if file_off >= len(self.data) or length <= 0:
                continue
            
            # Clamp length to physical file payload end to prevent out of bounds
            length = min(length, len(self.data) - file_off)
            
            sample_data = self.data[file_off : file_off + length]
            if len(sample_data) < 16: continue # skip garbage micro-samples
            
            wav_name = f"sample_{count:03d}_sa_{hex(sa)}_mode{mode}.wav"
            wav_path = os.path.join(output_dir, wav_name)
            
            success = self.convert_pcm_to_wav(
                sample_data, wav_path, 
                rate=22050, bits=bits, channels=1, 
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
