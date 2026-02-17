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
            
        found_samples = []
        # Scan first 4KB for SCSP Slot Descriptors
        for i in range(0, min(len(self.data), 4096), 2):
            if i + 32 > len(self.data): break
            slot0 = self._read_u16(i)
            # MD (Mode): 0=PCM8, 1=PCM16, 2=ADPCM
            mode = (slot0 >> 11) & 0x03
            if mode in [0, 1]: 
                sa_high = self.data[i+3] & 0x03
                sa_low = self._read_u16(i+4)
                sa = (sa_high << 16) | sa_low
                
                lea_high = self.data[i+11] & 0x03
                lea_low = self._read_u16(i+12)
                lea = (lea_high << 16) | lea_low
                
                if 0 <= sa < lea and (lea - sa) > 16:
                    if lea < 0x80000: # 512KB SCSP RAM
                        found_samples.append({'ptr': i, 'sa': sa, 'lea': lea, 'mode': mode})
        
        # Deduplicate
        unique_samples = []
        seen = set()
        for s in found_samples:
            key = (s['sa'], s['lea'], s['mode'])
            if key not in seen:
                unique_samples.append(s)
                seen.add(key)
        
        unique_samples.sort(key=lambda x: x['sa'])
        
        # Determine PCM start offset
        # Heuristic: PCM starts after all the voice/layer headers.
        first_ptr = self._read_u16(0)
        num_entries = first_ptr // 2
        max_ptr_target = 0
        for i in range(min(num_entries, 256)): # Safety cap
            ptr = self._read_u16(i * 2)
            if ptr != 0xFFFF and ptr < len(self.data):
                max_ptr_target = max(max_ptr_target, ptr)
        
        pcm_start = ((max_ptr_target + 128 + 0x3F) // 0x40) * 0x40
            
        print(f"Detected PCM start at {hex(pcm_start)}")
        
        count = 0
        for s in unique_samples:
            sa = s['sa']
            lea = s['lea']
            mode = s['mode']
            
            # SCSP Units: Bytes for PCM8, Words for PCM16
            if mode == 1:
                file_off = pcm_start + sa * 2
                length = (lea - sa) * 2
                bits = 16
            else:
                file_off = pcm_start + sa
                length = lea - sa
                bits = 8
            
            if file_off + length > len(self.data):
                continue
                
            sample_data = self.data[file_off : file_off + length]
            if not sample_data: continue
            
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
