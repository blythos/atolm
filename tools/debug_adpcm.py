import struct
import os
import argparse
import numpy as np
import wave

# Simple IMA ADPCM Decoder
index_table = [
    -1, -1, -1, -1, 2, 4, 6, 8,
    -1, -1, -1, -1, 2, 4, 6, 8
]

step_table = [
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

def decode_adpcm(data):
    samples = []
    predictor = 0
    step_index = 0
    
    # Header logic?
    # Usually ADPCM chunks on Saturn/FILM have a small header per chunk (4-16 bytes)
    # containing initial predictor/step or just size.
    # Let's try skipping 0, 4, 16 bytes.
    # Or assuming header contains state.
    
    # Try raw first (skip 0)
    # But usually high nibble / low nibble order matters.
    
    for byte in data:
        # High Nibble first?
        n1 = (byte >> 4) & 0x0F
        n2 = byte & 0x0F
        
        # Decode n1
        step = step_table[step_index]
        diff = step >> 3
        if n1 & 4: diff += step
        if n1 & 2: diff += (step >> 1)
        if n1 & 1: diff += (step >> 2)
        if n1 & 8: predictor -= diff
        else: predictor += diff
        predictor = max(-32768, min(32767, predictor))
        samples.append(predictor)
        step_index += index_table[n1]
        step_index = max(0, min(88, step_index))
        
        # Decode n2
        step = step_table[step_index]
        diff = step >> 3
        if n2 & 4: diff += step
        if n2 & 2: diff += (step >> 1)
        if n2 & 1: diff += (step >> 2)
        if n2 & 8: predictor -= diff
        else: predictor += diff
        predictor = max(-32768, min(32767, predictor))
        samples.append(predictor)
        step_index += index_table[n2]
        step_index = max(0, min(88, step_index))
        
    return samples

class SimpleCpkAudioDebug:
    def __init__(self, path):
        self.path = path
        with open(path, 'rb') as f:
            self.data = f.read()
        self.header = {}
        self.offset = 0
        self._parse()
        
    def _read_u32_be(self, offset):
        return struct.unpack('>I', self.data[offset:offset+4])[0]

    def _parse(self):
        self.offset = 16
        while self.offset < len(self.data):
             if self.offset + 8 > len(self.data): break
             val1 = self._read_u32_be(self.offset)
             if val1 >= 0x10000000:
                 chunk_size = self._read_u32_be(self.offset+4)
                 chunk_tag = self.data[self.offset:self.offset+4]
             else:
                 chunk_size = val1
                 chunk_tag = self.data[self.offset+4:self.offset+8]
             
             data_start = self.offset + 8
             payload_len = chunk_size - 8
             
             if chunk_tag == b'STAB':
                 self.data_base = self.offset + chunk_size
                 self._parse_stab(data_start, payload_len)
                 break
             
             self.offset += chunk_size

    def _parse_stab(self, offset, length):
        frame_count = self._read_u32_be(offset+4)
        table = offset + 16
        audio_chunks = []
        for i in range(frame_count):
            info1 = self._read_u32_be(table) # Flags/Info1
            info2 = self._read_u32_be(table+4)
            off = self._read_u32_be(table+8)
            size = self._read_u32_be(table+12)
            if info1 == 0xFFFFFFFF:
                audio_chunks.append((off, size))
            table += 16
        self.audio_chunks = audio_chunks

    def dump_adpcm(self, output_dir):
        if not self.audio_chunks: return
        print(f"Extracting ADPCM test...")
        
        # Try a few variants of skipping/decoding
        
        # Variant A: Continuous Decode (Skip 16 byte headers)
        samples_a = []
        # Reset predictor per file? Or per chunk?
        # Usually DVI is continuous or resets per block. 
        # Standard FILM is usually continuous state but we skip headers.
        
        for off, size in self.audio_chunks[:100]:
            abs_off = self.data_base + off
            chunk = self.data[abs_off : abs_off+size]
            if size > 16: chunk = chunk[16:]
            
            s = decode_adpcm(chunk)
            samples_a.extend(s)
            
        data_a = struct.pack(f'<{len(samples_a)}h', *samples_a)
        self._write_wav(os.path.join(output_dir, "test_adpcm_a.wav"), data_a, 1, 16)
        
        # Variant B: No Header Skip?
        samples_b = []
        for off, size in self.audio_chunks[:100]:
            abs_off = self.data_base + off
            chunk = self.data[abs_off : abs_off+size]
            # No skip
            s = decode_adpcm(chunk)
            samples_b.extend(s)

        data_b = struct.pack(f'<{len(samples_b)}h', *samples_b)
        self._write_wav(os.path.join(output_dir, "test_adpcm_b.wav"), data_b, 1, 16)

    def _write_wav(self, path, data, width, bit_depth):
        with wave.open(path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(bit_depth // 8)
            wf.setframerate(44100) 
            wf.writeframes(data)
        print(f"Saved {path}")

if __name__ == '__main__':
    debug = SimpleCpkAudioDebug('output/MOVIE1.CPK')
    debug.dump_adpcm('output/v2_test')
