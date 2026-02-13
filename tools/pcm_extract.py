#!/usr/bin/env python3
import argparse
import os
import sys
import struct
import wave
import numpy as np
import subprocess

# Add tools directory to path to import common modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from common.iso9660 import ISO9660Reader
except ImportError:
    # If running from within tools/ directly
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from common.iso9660 import ISO9660Reader

def parse_args():
    parser = argparse.ArgumentParser(description="Extract PCM audio from Sega Saturn disc images.")
    parser.add_argument("--disc", help="Path to the disc image (.bin/.iso)")
    parser.add_argument("--file", help="Specific file to extract (optional)")
    parser.add_argument("--output", default="pcm_output", help="Output directory")
    parser.add_argument("--rate", type=int, default=22050, help="Sample rate (default: 22050)")
    parser.add_argument("--bits", type=int, choices=[8, 16], default=16, help="Bit depth (default: 16)")
    parser.add_argument("--channels", type=int, default=1, help="Channels (default: 1)")
    parser.add_argument("--raw-file", help="Process a local raw PCM file instead of extracting from ISO")
    parser.add_argument("--big-endian", action="store_true", default=True, help="Treat input as big-endian (default: True)")
    parser.add_argument("--little-endian", action="store_false", dest="big_endian", help="Treat input as little-endian")
    parser.add_argument("--signed", action="store_true", default=True, help="Treat input as signed (default: True)")
    parser.add_argument("--unsigned", action="store_false", dest="signed", help="Treat input as unsigned")
    return parser.parse_args()

def convert_pcm_to_wav(pcm_data, output_path, rate, bits, channels, big_endian=True, signed=True):
    """Converts raw PCM data to WAV."""
    
    if bits == 16:
        # Saturn 16-bit is typically Big Endian Signed
        dtype_str = '>' if big_endian else '<'
        dtype_str += 'i2' if signed else 'u2'
        
        samples = np.frombuffer(pcm_data, dtype=dtype_str)
        
        # WAV expects Little Endian Signed 16-bit
        # If input was signed, we just need to swap endianness if it was BE
        # If input was unsigned, we need to shift it to signed? standard wav 16 is signed.
        
        if signed:
            # Just ensure little endian
            samples = samples.astype('<i2')
        else:
            # Unsigned 16 to Signed 16: subtract 32768
            samples = samples.astype(np.int32) - 32768
            samples = samples.astype('<i2')
            
    elif bits == 8:
        # Saturn 8-bit is typically Signed. WAV 8-bit is Unsigned.
        dtype_str = 'int8' if signed else 'uint8'
        samples = np.frombuffer(pcm_data, dtype=dtype_str)
        
        if signed:
            # Signed 8 (-128 to 127) to Unsigned 8 (0 to 255)
            samples = (samples.astype(np.int16) + 128).astype(np.uint8)
        else:
            # Already unsigned, no change needed for WAV
            pass
            
    else:
        raise ValueError(f"Unsupported bit depth: {bits}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with wave.open(output_path, 'wb') as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(bits // 8) # 1 byte for 8-bit, 2 bytes for 16-bit
        wav_file.setframerate(rate)
        wav_file.writeframes(samples.tobytes())
    
    return True

def probe_file(file_path):
    """Uses ffprobe to inspect a file."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_name,sample_rate,channels', '-of', 'default=noprint_wrappers=1:nokey=1', file_path],
            capture_output=True, text=True
        )
        return result.stdout.strip()
    except FileNotFoundError:
        return "FFmpeg not found"
    except Exception as e:
        return f"Error probing: {e}"

def main():
    args = parse_args()
    
    if args.raw_file:
        # Process a single local file
        print(f"Processing local file: {args.raw_file}")
        with open(args.raw_file, 'rb') as f:
            data = f.read()
            
        out_name = os.path.basename(args.raw_file) + ".wav"
        out_path = os.path.join(args.output, out_name)
        
        convert_pcm_to_wav(data, out_path, args.rate, args.bits, args.channels, args.big_endian, args.signed)
        print(f"Converted to {out_path}")
        return

    if not args.disc:
        print("Error: --disc argument or --raw-file is required.")
        sys.exit(1)

    if not os.path.exists(args.disc):
        print(f"Error: Disc image not found: {args.disc}")
        sys.exit(1)

    print(f"Opening disc image: {args.disc}")
    iso = ISO9660Reader(args.disc)
    
    files = iso.list_files()
    pcm_files = [f for f in files if f['name'].upper().endswith('.PCM')]
    
    if not pcm_files:
        print("No .PCM files found on disc.")
        sys.exit(0)
        
    print(f"Found {len(pcm_files)} PCM files.")
    
    if args.file:
        # Filter for specific file
        target = args.file.upper()
        pcm_files = [f for f in pcm_files if f['name'].upper() == target]
        if not pcm_files:
            print(f"File {args.file} not found in PCM list.")
            sys.exit(1)
            
    for pcm_file in pcm_files:
        print(f"Extracting {pcm_file['name']} ({pcm_file['size']} bytes)...")
        data = iso.extract_file(pcm_file['lba'], pcm_file['size'])
        
        # Heuristic check for header (TODO: Research actual header format)
        # For now, we assume raw data as per task description, but we can print first few bytes for debug
        # print(f"Header bytes: {data[:16].hex()}")
        
        out_name = pcm_file['name'] + ".wav"
        out_path = os.path.join(args.output, out_name)
        
        convert_pcm_to_wav(data, out_path, args.rate, args.bits, args.channels, args.big_endian, args.signed)
        print(f"Saved to {out_path}")
        
    iso.close()
    print("Done.")

if __name__ == "__main__":
    main()
