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
    """Parser for Sega FILM/CPK container format.
    
    Reference: https://multimedia.cx/film-format.txt (Mike Melanson)
    Reference: FFmpeg libavformat/segafilm.c (film_read_header)
    
    FILM header (16 bytes):
      bytes 0-3:   'FILM' signature
      bytes 4-7:   total header length (= offset to sample data start)
      bytes 8-11:  version string (e.g. '1.07')
      bytes 12-15: reserved (0)
    
    FDSC chunk (32 bytes, standard Saturn):
      bytes 0-3:   'FDSC' signature
      bytes 4-7:   chunk length (0x20 = 32)
      bytes 8-11:  video codec FOURCC ('cvid')
      bytes 12-15: video height (u32 BE)
      bytes 16-19: video width (u32 BE)
      byte 20:     unknown (0x18)
      byte 21:     audio channels
      byte 22:     audio bit depth (8 or 16)
      byte 23:     unknown
      bytes 24-25: audio sample rate (u16 BE)
      bytes 26-31: reserved
    
    STAB chunk:
      bytes 0-3:   'STAB' signature
      bytes 4-7:   chunk length
      bytes 8-11:  base clock frequency (Hz)
      bytes 12-15: number of sample table entries
      bytes 16+:   sample records (16 bytes each)
    
    Each sample record:
      bytes 0-3:   offset from start of sample data
      bytes 4-7:   size of sample chunk
      bytes 8-11:  info1 (0xFFFFFFFF = audio; else video timestamp)
      bytes 12-15: info2 (video: ticks to next frame; audio: always 1)
    """
    def __init__(self, data):
        self.data = data
        self._parse()
        
    def _parse(self):
        if self.data[0:4] != b'FILM':
            raise ValueError("Not a FILM file")
            
        # bytes 4-7: total header length = offset to start of sample data
        self.data_base_offset = read_u32_be(self.data, 4)
        version = self.data[8:12].decode('ascii', errors='ignore')
        print(f"FILM: header_len={self.data_base_offset}, version='{version}'")
        
        # Sub-chunks start at offset 16 (after FILM preamble)
        offset = 16
        while offset < self.data_base_offset:
            chunk_sig = self.data[offset:offset+4].decode('ascii', errors='ignore')
            chunk_len = read_u32_be(self.data, offset+4)
            
            if chunk_sig == 'FDSC':
                self._parse_fdsc(offset)
            elif chunk_sig == 'STAB':
                self._parse_stab(offset, chunk_len)
            
            # chunk_len includes the 8-byte sig+length header
            offset += chunk_len

    def _parse_fdsc(self, base):
        """Parse FDSC chunk. Offsets are from chunk start."""
        codec = self.data[base+8:base+12].decode('ascii', errors='ignore')
        height = read_u32_be(self.data, base+12)
        width = read_u32_be(self.data, base+16)
        channels = self.data[base+21]
        bit_depth = self.data[base+22]
        sample_rate = struct.unpack('>H', self.data[base+24:base+26])[0]
        
        # Defensive defaults
        if channels == 0: channels = 1
        if bit_depth == 0: bit_depth = 16
        
        print(f"  FDSC: {width}x{height} {codec}, {channels}ch {bit_depth}bit {sample_rate}Hz")
        
        self.header = {
            'width': width, 'height': height, 'codec': codec,
            'bit_depth': bit_depth, 'channels': channels,
            'sample_rate': sample_rate,
        }

    def _parse_stab(self, base, chunk_len):
        """Parse STAB chunk. Offsets are from chunk start."""
        self.stab_base_freq = read_u32_be(self.data, base+8)
        num_entries = read_u32_be(self.data, base+12)
        print(f"  STAB: base_freq={self.stab_base_freq}Hz, {num_entries} entries")
        
        self.stab_entries = []
        audio_count = 0
        video_count = 0
        
        for i in range(num_entries):
            rec = base + 16 + i * 16
            if rec + 16 > base + chunk_len:
                break
            
            # Standard Sega FILM record layout (confirmed by FFmpeg source):
            #   bytes 0-3: offset, 4-7: size, 8-11: info1, 12-15: info2
            sample_offset = read_u32_be(self.data, rec)
            sample_size   = read_u32_be(self.data, rec+4)
            info1         = read_u32_be(self.data, rec+8)
            info2         = read_u32_be(self.data, rec+12)
            
            self.stab_entries.append({
                'offset': sample_offset,
                'size': sample_size,
                'info1': info1,
                'info2': info2,
            })
            
            # Per spec + FFmpeg: info1 == 0xFFFFFFFF means audio
            if info1 == 0xFFFFFFFF:
                audio_count += 1
            else:
                video_count += 1

        print(f"  STAB: parsed {len(self.stab_entries)} ({video_count} video, {audio_count} audio)")

    def extract_audio(self):
        """Extract interleaved audio chunks to WAV-ready PCM data.
        
        Per spec: audio chunks have info1 == 0xFFFFFFFF.
        Data is signed PCM, big-endian for 16-bit, at sample offsets
        relative to data_base_offset.
        """
        if not hasattr(self, 'data_base_offset'):
            return b''
            
        base = self.data_base_offset
        channels = self.header.get('channels', 1)
        if channels == 0: channels = 1
        bit_depth = self.header.get('bit_depth', 16)
        
        audio_entries = [e for e in self.stab_entries if e['info1'] == 0xFFFFFFFF]
        print(f"  Extracting {len(audio_entries)} audio chunks...")
        
        audio_parts = []
        for entry in audio_entries:
            offset = base + entry['offset']
            size = entry['size']
            
            if offset + size > len(self.data):
                print(f"    Warning: chunk out of bounds (offset={offset}, size={size})")
                continue
                
            chunk = self.data[offset:offset+size]
            if not chunk:
                continue
            
            if bit_depth == 16:
                if len(chunk) % 2 != 0:
                    chunk = chunk[:-1]
                samples = np.frombuffer(chunk, dtype='>i2')  # BE Signed 16
            else:
                samples = np.frombuffer(chunk, dtype='i1')   # Signed 8
                            
            audio_parts.append(samples)
                
        if not audio_parts:
            print("  No audio chunks found.")
            return b''

        audio_data = np.concatenate(audio_parts)
        
        # Convert to Little Endian for WAV
        if bit_depth == 16:
            return audio_data.astype('<i2').tobytes()
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

    def process_cpk_file(cpk_path):
        print(f"Processing {os.path.basename(cpk_path)}...")
        wav_path = os.path.splitext(cpk_path)[0] + ".wav"
        mp4_path = os.path.splitext(cpk_path)[0] + ".mp4"
        
        with open(cpk_path, 'rb') as f:
            data = f.read()
            
        try:
            film = SegaFilmParser(data)
            wav_data = film.extract_audio()
            
            if wav_data:
                # Use FDSC sample rate if plausible, else default to 32000
                sr = film.header.get('sample_rate', 0)
                if sr < 8000 or sr > 48000:
                    sr = 32000
                write_wav(wav_path, wav_data, 
                          film.header.get('channels', 1),
                          sr, 
                          film.header.get('bit_depth', 16))
                print(f"  Saved Audio: {wav_path} ({sr}Hz)")
                
        except Exception as e:
            print(f"  Error parsing: {e}")
            import traceback
            traceback.print_exc()

        if ffmpeg_exe:
            inputs = ['-i', cpk_path]
            map_args = ['-map', '0:v']
            
            # Map Audio: Use extracted WAV if it exists, else try FFmpeg's internal decoder
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
