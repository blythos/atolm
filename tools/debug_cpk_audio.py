import struct
import os
import argparse
import numpy as np
import wave

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
        # Quick skip to STAB
        # Header 16 bytes
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
        print(f"STAB Frames: {frame_count}")
        table = offset + 16
        
        self.all_entries = []
        audio_chunks = []
        for i in range(frame_count):
            info1 = self._read_u32_be(table)
            info2 = self._read_u32_be(table+4) # Added info2 read
            off = self._read_u32_be(table+8)
            size = self._read_u32_be(table+12)
            
            self.all_entries.append((off, size, info1, info2)) # Populate all_entries
            
            if info1 == 0xFFFFFFFF:
                audio_chunks.append((off, size, info2)) # Added info2 to audio_chunks append
                
            table += 16
            
        self.audio_chunks = audio_chunks
        print(f"Found {len(audio_chunks)} audio chunks")

    def dump_variants(self, output_dir):
        if not self.audio_chunks:
            print("No audio chunks found.")
            return

        print(f"Extracting first 20 chunks for detailed analysis...")
        
        # STAB Group Analysis
        print("--- STAB Info2 Analysis ---")
        info2_groups = {}
        for off, size, info1, info2 in self.all_entries:
            if info2 not in info2_groups: info2_groups[info2] = []
            info2_groups[info2].append(info1)
            
        for i2, i1_list in info2_groups.items():
            print(f"Info2={i2:X} (Size={len(i1_list)}): [First 3 I1: {', '.join(f'{x:X}' for x in i1_list[:3])}]")
            
        print("\n--- Audio Chunk Header Analysis (Sample) ---")
        audio_candidates = [e for e in self.all_entries if e[2] != 0xFFFFFFFF]
        
        # Check first 5, middle 5
        indices = list(range(5)) + list(range(len(audio_candidates)//2, len(audio_candidates)//2 + 5))
        
        for idx in indices:
            if idx >= len(audio_candidates): continue
            off, size, info1, info2 = audio_candidates[idx]
            abs_off = self.data_base + off
            chunk = self.data[abs_off : abs_off+min(32, size)]
            print(f"Chunk {idx} (Sz={size}, I1={info1:X}, I2={info2:X}): {chunk.hex()}")
        
        self.audio_chunks = [(e[0], e[1]) for e in audio_candidates] # Use these for audio extraction test

        # Collect raw payload
        raw_payload = bytearray()
        for off, size in self.audio_chunks[:20]: # First 20 chunks (~1 sec?)
            abs_off = self.data_base + off
            chunk = self.data[abs_off : abs_off+size]
            
            # Strip header?
            if size > 16:
                chunk = chunk[16:]
            
            raw_payload.extend(chunk)
            
        # Variant 1: 16-bit BE Signed (Current Logic) -> Swap to LE
        data_be = np.frombuffer(raw_payload, dtype='>i2').astype('<i2').tobytes()
        self._write_wav(os.path.join(output_dir, "test_16be_signed.wav"), data_be, 2, 16)
        
        # Variant 2: 16-bit LE Signed (Assume already LE) -> No Swap
        # But wait, numpy frombuffer defaults to machine endian (LE on x86).
        # So dtype='i2' or '<i2' reads as LE.
        data_le = np.frombuffer(raw_payload, dtype='<i2').tobytes()
        self._write_wav(os.path.join(output_dir, "test_16le_signed.wav"), data_le, 2, 16)
        
        # Variant 3: 8-bit Signed
        # Wav needs Unsigned 8-bit.
        data_s8 = np.frombuffer(raw_payload, dtype='b') # Signed
        data_u8 = (data_s8.astype(np.int16) + 128).astype(np.uint8).tobytes()
        self._write_wav(os.path.join(output_dir, "test_8_signed.wav"), data_u8, 1, 8)
        
        # Variant 4: 8-bit Unsigned (Already Unsigned?)
        data_raw_8 = raw_payload # Raw bytes
        self._write_wav(os.path.join(output_dir, "test_8_unsigned.wav"), data_raw_8, 1, 8)

        # Variant 5: 16-bit BE Mono (Just in case)
        self._write_wav(os.path.join(output_dir, "test_16be_mono.wav"), data_be, 1, 16)

        # Variant 6: 16-bit LE Mono
        self._write_wav(os.path.join(output_dir, "test_16le_mono.wav"), data_le, 1, 16)

    def _write_wav(self, path, data, width, bit_depth):
        with wave.open(path, 'wb') as wf:
            wf.setnchannels(1) # Force mono for now to rule out interleaving
            wf.setsampwidth(bit_depth // 8)
            wf.setframerate(44100) # Assume 44.1 for now
            wf.writeframes(data)
        print(f"Saved {path}")

    def check_coverage(self):
        print("--- File Coverage Analysis ---")
        total_param_size = 0
        min_off = float('inf')
        max_end = 0
        
        for off, size, i1, i2 in self.all_entries:
             abs_off = self.data_base + off
             total_param_size += size
             min_off = min(min_off, abs_off)
             max_end = max(max_end, abs_off + size)
             
        print(f"File Size: {len(self.data)}")
        print(f"Data Base: {self.data_base}")
        print(f"Min Offset: {min_off}")
        print(f"Max End: {max_end}")
        print(f"Total Chunk Size: {total_param_size}")
        print(f"Uncovered Bytes: {len(self.data) - max_end}")
        
        # Check if STAB table continues
        # frame_count in STAB header might be just video frames?
        # Try reading past frame_count?
        
        # Or check gap between STAB and Data Base?
        
    def check_sizes(self):
        print("--- Size Mismatch Analysis ---")
        mismatches = []
        for i, (off, size, i1, i2) in enumerate(self.all_entries):
             abs_off = self.data_base + off
             if abs_off + 4 > len(self.data): continue
             
             # Read first 4 bytes as Big Endian size
             h_size = struct.unpack('>I', self.data[abs_off:abs_off+4])[0]
             
             delta = size - h_size
             if delta != 8: # Expect 8 bytes diff usually?
                 mismatches.append((i, size, h_size, delta, i1, i2))
                 
        print(f"Found {len(mismatches)} chunks with Delta != 8")
        for i, size, h_size, delta, i1, i2 in mismatches[:20]:
            print(f"Chunk {i}: STAB={size} Header={h_size} Delta={delta} (I1={i1:X}, I2={i2:X})")
            
if __name__ == '__main__':
    debug = SimpleCpkAudioDebug('output/MOVIE1.CPK')
    debug.check_sizes()

