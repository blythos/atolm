import struct
import os
import argparse
import sys
import numpy as np
import subprocess
import shutil

from common.iso9660 import ISO9660Reader
from common.saturn import read_u32_be

class SegaFilmParser:
    def __init__(self, data):
        self.data = data
        self.offset = 0
        self._parse()
        
    def _parse(self):
        if self.data[0:4] != b'FILM':
            raise ValueError("Not a FILM file")
            
        file_len = read_u32_be(self.data, 4)
        print(f"File Length: {file_len}")
        
        self.offset = 16 # Skip 'FILM' + Size + Version + Reserved?
        
        while self.offset < len(self.data):
            chunk_sig = self.data[self.offset:self.offset+4].decode('ascii', errors='ignore')
            chunk_size = read_u32_be(self.data, self.offset+4)
            
            print(f"Chunk: {chunk_sig}, Size: {chunk_size}")
            
            if chunk_sig == 'FDSC':
                self._parse_fdsc(self.offset+8, chunk_size-8)
            elif chunk_sig == 'STAB':
                self._parse_stab(self.offset+8, chunk_size-8)
                self.data_base_offset = self.offset + chunk_size
                break # Usually nothing after STAB except data
            
            self.offset += chunk_size

    def _parse_fdsc(self, offset, length):
        codec = self.data[offset:offset+4].decode('ascii', errors='ignore')
        height = read_u32_be(self.data, offset+4)
        width = read_u32_be(self.data, offset+8)
        # Audio params
        channels = self.data[offset+13]
        if channels == 0: channels = 1
        bit_depth = self.data[offset+14]
        if bit_depth == 0: bit_depth = 16
        
        print(f"  FDSC Info: {width}x{height} {codec}, Audio: {channels}ch {bit_depth}bit")
        
        self.header = {
            'width': width, 'height': height, 'codec': codec,
            'bit_depth': bit_depth, 'channels': channels
        }
        
        # Sample Rate is unreliable in FDSC for these files
        # We will enforce 32000 in extract_audio

    def _parse_stab(self, offset, length):
        # STAB Header (within payload)
        frame_count = read_u32_be(self.data, offset+4)
        print(f"  STAB Info: {frame_count} frames")
        
        # Chunk Table Entries (16 bytes each)
        table_offset = offset + 8
        self.stab_entries = []
        
        audio_chunk_count = 0
        
        for i in range(frame_count):
            if table_offset + 16 > offset + length: break
            
            info1 = read_u32_be(self.data, table_offset)
            info2 = read_u32_be(self.data, table_offset+4)
            off = read_u32_be(self.data, table_offset+8)
            size = read_u32_be(self.data, table_offset+12)
            
            off = off & 0x7FFFFFFF

            if off == 0x7FFFFFFF:
                table_offset += 16
                continue

            self.stab_entries.append({'offset': off, 'size': size, 'info1': info1, 'info2': info2})
            if info1 != 0xFFFFFFFF:
                 audio_chunk_count += 1

            table_offset += 16
            
        print(f"  STAB Entries found: {len(self.stab_entries)}")
        print(f"  Potential Audio Chunks: {audio_chunk_count}")


    def extract_audio(self):
        """Extract audio to WAV-ready PCM data."""
        if not hasattr(self, 'data_base_offset'):
            return b''
            
        base = self.data_base_offset
        channels = self.header.get('channels', 1)
        if channels == 0: channels = 1 # Force valid channel count
        
        bit_depth = self.header.get('bit_depth', 16)
        
        audio_parts = []
        
        print(f"  Extracting Audio ({len(self.stab_entries)} table entries)...")
        
        for entry in self.stab_entries:
            if entry['info1'] != 0xFFFFFFFF: 
                # Potential Audio Chunk (Info2=0x28 typically)
                # But some Info2=0x28 chunks are actually Video Metadata/Interframes.
                
                offset = base + entry['offset']
                size = entry['size']
                
                if offset + size > len(self.data):
                    print(f"    Warning: Audio chunk out of bounds (Offset {offset}, Size {size})")
                    continue
                    
                chunk = self.data[offset : offset+size]
                
                # Content-Aware Checks
                is_video = False
                if size >= 4:
                    h_val_raw = struct.unpack('>I', chunk[0:4])[0]
                    # Mask out the first byte (Flags?) to check size
                    # Video headers often 00 00 Size OR 01 00 Size
                    h_val = h_val_raw & 0x00FFFFFF
                    
                    if h_val == size or h_val == size - 8 or h_val == size - 4:
                        is_video = True
                    
                if is_video:
                    continue
                        
                # It's Audio.
                if not chunk: continue
                
                # Conversion
                if bit_depth == 16:
                    samples = np.frombuffer(chunk, dtype='>i2') # BE Signed 16
                else:
                    samples = np.frombuffer(chunk, dtype='i1') # Signed 8
                                
                audio_parts.append(samples)
                
        if not audio_parts:
             print("  No audio chunks found.")
             return b''

        audio_data = np.concatenate(audio_parts)
        
        # WAV Creation
        # Enforce 32000 Hz for Panzer Dragoon Saga
        sample_rate = 32000 
        
        # Convert to Bytes (Little Endian for WAV)
        if bit_depth == 16:
             audio_data_le = audio_data.astype('<i2')
             return audio_data_le.tobytes()
        else:
             return audio_data.tobytes()

def write_wav(filename, audio_data, channels, sample_rate, bit_depth):
    import wave
    with wave.open(filename, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(bit_depth // 8)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_data)

def check_ffmpeg(local_path='tools/ffmpeg.exe'):
    if shutil.which('ffmpeg'):
        return 'ffmpeg'
    if os.path.exists(local_path):
        return os.path.abspath(local_path)
    return None

def main():
    parser = argparse.ArgumentParser(description="CPK Extractor v2")
    parser.add_argument('--disc', help="Path to single ISO image")
    parser.add_argument('--cpk', help="Path to single CPK file")
    parser.add_argument('--batch-folder', help="Process all ISO/BIN files in folder")
    parser.add_argument('--clean', action='store_true', help="Delete intermediate WAV/CPK files")
    parser.add_argument('--output', default="output/videos", help="Output directory")
    args = parser.parse_args()
    
    if not os.path.exists(args.output):
        os.makedirs(args.output)
    
    ffmpeg_exe = check_ffmpeg() 
    if not ffmpeg_exe:
        if os.path.exists('tools/ffmpeg.exe'): 
            ffmpeg_exe = os.path.abspath('tools/ffmpeg.exe')
        else:
            print("Warning: FFmpeg not found. Video conversion will be skipped.")

    # Helper function
    def process_cpk_file(cpk_path):
        print(f"Processing {os.path.basename(cpk_path)}...")
        wav_path = os.path.splitext(cpk_path)[0] + ".wav"
        mp4_path = os.path.splitext(cpk_path)[0] + ".mp4"
        
        with open(cpk_path, 'rb') as f:
            data = f.read()
            
        try:
            parser = SegaFilmParser(data)
            wav_data = parser.extract_audio()
            
            if wav_data:
                write_wav(wav_path, wav_data, 
                          parser.header.get('channels', 1),
                          32000, 
                          parser.header.get('bit_depth', 16))
                print(f"  Saved Audio: {wav_path}")
                
        except Exception as e:
            print(f"  Error parsing: {e}")
            import traceback
            traceback.print_exc()

        if ffmpeg_exe:
            inputs = ['-i', cpk_path]
            map_args = ['-map', '0:v']
            
            # Map Audio: Use extracted WAV if it exists, else use FFmpeg's internal decoder
            if os.path.exists(wav_path):
                inputs += ['-i', wav_path]
                map_args += ['-map', '1:a']
            else:
                map_args += ['-map', '0:a?']

            # Map Subtitles: Search for matching SRT file
            srt_name = os.path.splitext(os.path.basename(cpk_path))[0] + ".srt"
            srt_search_paths = [
                os.path.join("output/subtitles", srt_name),
                os.path.join("subtitles", srt_name)
            ]
            srt_path = next((p for p in srt_search_paths if os.path.exists(p)), None)
            
            sub_args = []
            if srt_path:
                print(f"  Found Subtitles: {srt_path}")
                inputs += ['-i', srt_path]
                sub_idx = inputs.count('-i') - 1
                map_args += ['-map', f'{sub_idx}:s']
                sub_args = [
                    '-c:s', 'mov_text', 
                    '-metadata:s:s:0', 'title=English', 
                    '-metadata:s:s:0', 'language=eng',
                    '-disposition:s:0', 'default'
                ]

            cmd = [
                ffmpeg_exe, 
                *inputs,
                *map_args,
                '-c:v', 'libx264', '-crf', '18',
                '-pix_fmt', 'yuv420p', 
                *sub_args,
                '-y', mp4_path,
                '-hide_banner', '-loglevel', 'error'
            ]
            
            try:
                subprocess.run(cmd, check=True)
                print(f"  Saved Video: {mp4_path}")
                
                # Cleanup
                if args.batch_folder or args.clean:
                    if os.path.exists(wav_path): os.remove(wav_path)
                    if os.path.exists(cpk_path): os.remove(cpk_path)
                    print("  Cleaned up intermediate files.")
                    
            except subprocess.CalledProcessError:
                print(f"  FFmpeg failed to convert {cpk_path}")

    # Batch Processing
    if args.batch_folder:
        if not os.path.exists(args.batch_folder):
            print(f"Error: Batch folder {args.batch_folder} not found.")
            sys.exit(1)

        print(f"Scanning {args.batch_folder} for ISO/BIN files...")
        iso_files = [os.path.join(args.batch_folder, f) for f in os.listdir(args.batch_folder) if f.lower().endswith(('.iso', '.bin'))]
        
        if not iso_files:
            print("No ISO/BIN files found.")

        for iso_path in iso_files:
            print(f"\nProcessing Disc Image: {os.path.basename(iso_path)}")
            try:
                iso = ISO9660Reader(iso_path)
                files = iso.list_files()
                cpk_entries = [f for f in files if f['name'].upper().endswith('.CPK')]
                print(f"  Found {len(cpk_entries)} CPK files.")
                
                for entry in cpk_entries:
                    print(f"  Extracting {entry['name']}...")
                    data = iso.extract_file(entry['lba'], entry['size'])
                    
                    # Temp file for processing
                    cpk_temp = os.path.join(args.output, entry['name'])
                    with open(cpk_temp, 'wb') as f:
                        f.write(data)
                        
                    process_cpk_file(cpk_temp)
                        
                iso.close()
            except Exception as e:
                print(f"  Error processing disc {iso_path}: {e}")

    # Single Disc Mode
    elif args.disc:
        if not os.path.exists(args.disc):
            print(f"Error: Disc image {args.disc} not found.")
            sys.exit(1)
            
        print(f"Opening disc image: {args.disc}")
        iso = ISO9660Reader(args.disc)
        files = iso.list_files()
        cpk_entries = [f for f in files if f['name'].upper().endswith('.CPK')]
        print(f"Found {len(cpk_entries)} CPK files on disc.")
        
        for entry in cpk_entries:
            print(f"Extracting {entry['name']}...")
            data = iso.extract_file(entry['lba'], entry['size'])
            out_path = os.path.join(args.output, entry['name'])
            with open(out_path, 'wb') as f:
                f.write(data)
            
            process_cpk_file(out_path)
            
        iso.close()

    # Single CPK Mode
    elif args.cpk:
        if os.path.exists(args.cpk):
            process_cpk_file(args.cpk)
            
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
