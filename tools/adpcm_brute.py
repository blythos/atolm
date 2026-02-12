
import struct
import wave
import os
import argparse

# Standard DVI/IMA Tables
INDEX_TABLE = [
    -1, -1, -1, -1, 2, 4, 6, 8,
    -1, -1, -1, -1, 2, 4, 6, 8
]

STEP_TABLE = [
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17,
    19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
    50, 55, 60, 66, 73, 80, 88, 97, 107, 118,
    130, 143, 157, 173, 190, 209, 230, 253, 279, 307,
    337, 371, 408, 449, 494, 544, 598, 658, 724, 796,
    876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
    2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358,
    5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899,
    15290, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767
]

class AdpcmVariant:
    def __init__(self, name, nibble_order, endianness):
        self.name = name
        self.nibble_order = nibble_order # 'hi_lo' or 'lo_hi'
        self.endianness = endianness # 'be' or 'le'
        
        self.predictor = 0
        self.step_index = 0
        
    def decode(self, data):
        samples = []
        # Pre-process endianness if needed?
        # Actually nibble process handles single byte.
        # But if LE, data stream might be different?
        # No, ADPCM is byte stream.
        
        processed_data = data
        
        for byte in processed_data:
            n1 = 0
            n2 = 0
            
            if self.nibble_order == 'hi_lo':
                n1 = (byte >> 4) & 0x0F
                n2 = byte & 0x0F
            else:
                n1 = byte & 0x0F
                n2 = (byte >> 4) & 0x0F
                
            self._decode_nibble(n1, samples)
            self._decode_nibble(n2, samples)
            
        return samples

    def _decode_nibble(self, nibble, samples):
        step = STEP_TABLE[self.step_index]
        diff = step >> 3
        
        if nibble & 4: diff += step
        if nibble & 2: diff += (step >> 1)
        if nibble & 1: diff += (step >> 2)
        
        if nibble & 8:
            self.predictor -= diff
        else:
            self.predictor += diff
            
        # Clamp predictor
        self.predictor = max(-32768, min(32767, self.predictor))
        
        samples.append(self.predictor)
        
        # Update index
        self.step_index += INDEX_TABLE[nibble & 7]
        self.step_index = max(0, min(88, self.step_index))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input_file', help="Input raw adpcm bytes (or extracted wav to skip header)")
    parser.add_argument('--offset', type=int, default=0, help="Skip N bytes")
    parser.add_argument('--length', type=int, default=32000, help="Process N bytes")
    args = parser.parse_args()
    
    with open(args.input_file, 'rb') as f:
        f.seek(args.offset)
        data = f.read(args.length)
        
    print(f"Read {len(data)} bytes from {args.input_file}")
    
    variants = [
        AdpcmVariant("std_hilo", "hi_lo", "be"),
        AdpcmVariant("lohi", "lo_hi", "be"),
        # Other variants?
        # Maybe Signed/Unsigned predictor? (Unlikely for ADPCM)
        # Maybe Index Table offset?
    ]
    
    for v in variants:
        # Reset per file
        # Actually decoder resets.
        samples = v.decode(data)
        
        # Save WAV
        out_name = f"brute_{v.name}.wav"
        with wave.open(out_name, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(32000) # Standard Saturn
            
            # Pack LE
            out_bytes = struct.pack(f'<{len(samples)}h', *samples)
            w.writeframes(out_bytes)
        print(f"Generated {out_name}")

if __name__ == '__main__':
    main()
