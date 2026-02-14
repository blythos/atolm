import os
import subprocess
import sys
import shutil
import glob
import argparse
import re

def run_command(cmd):
    """Run a subprocess command."""
    print(f"Running: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        # Build critical? In batch process, maybe just log and continue to next disc?
        # For now, let's raise so we know.
        raise e

def parse_cue_for_bin(cue_path):
    """Parses a CUE file to find the first BIN track."""
    bin_filename = None
    try:
        with open(cue_path, 'r') as f:
            for line in f:
                # FILE "Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin" BINARY
                match = re.search(r'FILE "(.*)" BINARY', line)
                if match:
                    bin_filename = match.group(1)
                    break 
    except Exception as e:
        print(f"Error reading CUE file: {e}")
        return None
        
    if bin_filename:
        # Resolve relative path
        cue_dir = os.path.dirname(cue_path)
        return os.path.join(cue_dir, bin_filename)
    return None

def detect_disc_name(filename):
    """Extracts disc number from filename or defaults to basename."""
    base = os.path.basename(filename)
    # Check for "Disc X"
    match = re.search(r"Disc\s*(\d+)", base, re.IGNORECASE)
    if match:
        return f"Disc_{match.group(1)}"
    
    # Fallback: Just use cleaned filename
    return os.path.splitext(base)[0].replace(" ", "_")

def process_disc(bin_path, output_root):
    """
    Process a single disc (BIN file).
    1. Identify output subdirectory (e.g. output/Disc_1)
    2. Extract subs
    3. Extract CPK/WAV
    4. Mux
    5. Cleanup
    """
    print(f"\n=== Processing: {os.path.basename(bin_path)} ===")
    
    disc_folder_name = detect_disc_name(bin_path)
    disc_output_dir = os.path.join(output_root, disc_folder_name)
    subtitles_dir = os.path.join(disc_output_dir, "subtitles")
    
    # Create temp dir within output to avoid cross-drive issues
    temp_assets_dir = os.path.join(disc_output_dir, "temp_assets")
    
    os.makedirs(subtitles_dir, exist_ok=True)
    os.makedirs(temp_assets_dir, exist_ok=True)
    
    # 1. Extract Subtitles
    print(f"Step 1: Extracting Subtitles...")
    cmd_subs = [
        sys.executable, os.path.join(os.path.dirname(__file__), "extract_subtitles.py"),
        "--iso", bin_path,
        "--output", subtitles_dir,
        "--method", "dat",
        "--fps", "30.0"
    ]
    try:
        run_command(cmd_subs)
    except subprocess.CalledProcessError:
        print("Subtitle extraction failed. Skipping disc.")
        return

    # 2. Extract Assets (Audio Only mode for speed)
    print(f"Step 2: Extracting CPK assets...")
    # Clean temp dir contents if any
    for f in os.listdir(temp_assets_dir):
        p = os.path.join(temp_assets_dir, f)
        if os.path.isdir(p): shutil.rmtree(p)
        else: os.remove(p)

    cmd_cpk = [
        sys.executable, os.path.join(os.path.dirname(__file__), "cpk_extract.py"),
        "--disc", bin_path,
        "--output", temp_assets_dir,
        "--audio-only"
    ]
    try:
        run_command(cmd_cpk)
    except subprocess.CalledProcessError:
        print("CPK extraction failed. Skipping disc.")
        return

    # 3. Mux Videos
    print(f"Step 3: Muxing Videos...")
    cpk_files = [f for f in os.listdir(temp_assets_dir) if f.upper().endswith('.CPK')]
    
    # Find ffmpeg
    ffmpeg_exe = "ffmpeg"
    local_ffmpeg = os.path.join(os.path.dirname(__file__), "ffmpeg.exe")
    if os.path.exists(local_ffmpeg):
        ffmpeg_exe = os.path.abspath(local_ffmpeg)
        
    for cpk_file in cpk_files:
        base_name = os.path.splitext(cpk_file)[0]
        
        # Subtitle Lookup
        srt_path = os.path.join(subtitles_dir, base_name + ".srt")
        if not os.path.exists(srt_path):
            # Case insensitive check
            for s in os.listdir(subtitles_dir):
                if s.lower() == (base_name + ".srt").lower():
                    srt_path = os.path.join(subtitles_dir, s)
                    break
        
        has_subs = os.path.exists(srt_path)
        
        # Paths
        cpk_path = os.path.join(temp_assets_dir, cpk_file)
        wav_path = os.path.join(temp_assets_dir, base_name + ".wav")
        mp4_path = os.path.join(disc_output_dir, base_name + ".mp4")
        
        # Build FFmpeg command
        inputs = ['-i', cpk_path]
        map_args = ['-map', '0:v']
        
        if os.path.exists(wav_path):
            inputs += ['-i', wav_path]
            map_args += ['-map', '1:a']
        else:
            map_args += ['-map', '0:a?'] # Use internal audio if no external WAV
            
        sub_args = []
        if has_subs:
            inputs += ['-i', srt_path]
            # Calculate stream index for substitutions
            sub_idx = len(inputs) // 2 - 1 
            # (Wait, -i x, -i y. inputs list is [-i, x, -i, y]. len is 4. indices 1, 3. 
            # count('-i') is safer.
            sub_idx = inputs.count('-i') - 1
            
            map_args += ['-map', f'{sub_idx}:s']
            sub_args = [
                '-c:s', 'mov_text',
                '-metadata:s:s:0', 'title=English',
                '-metadata:s:s:0', 'language=eng',
                '-disposition:s:0', 'default'
            ]
            print(f"  Muxing {base_name} [Subtitle: English]")
        else:
            print(f"  Muxing {base_name} [No Subtitles]")
            
        cmd_ffmpeg = [
            ffmpeg_exe,
            *inputs,
            *map_args,
            '-c:v', 'libx264', '-crf', '18',
            '-pix_fmt', 'yuv420p',
            '-aac_coder', 'twoloop',
            *sub_args,
            '-y', mp4_path,
            '-hide_banner', '-loglevel', 'error'
        ]
        
        try:
            subprocess.run(cmd_ffmpeg, check=True)
        except subprocess.CalledProcessError as e:
            print(f"  Failed to mux {base_name}: {e}")

    # 4. Cleanup
    print(f"Step 4: Cleanup temp assets...")
    shutil.rmtree(temp_assets_dir)

def main():
    parser = argparse.ArgumentParser(description="Batch process Sega Saturn FMVs (Extraction + Subtitles + Muxing)")
    parser.add_argument("input", help="Input file (.cue/.bin) or directory containing disc images")
    parser.add_argument("--output", help="Output directory (defaults to input_dir/processed_fmvs)")
    
    args = parser.parse_args()
    
    # Identify discs to process
    discs_to_process = [] # List of bin_paths
    
    if os.path.isfile(args.input):
        ext = os.path.splitext(args.input)[1].lower()
        if ext == '.cue':
            bin_path = parse_cue_for_bin(args.input)
            if bin_path and os.path.exists(bin_path):
                discs_to_process.append(bin_path)
            else:
                print(f"Error: Could not resolve BIN file from CUE: {args.input}")
                sys.exit(1)
        elif ext == '.bin' or ext == '.iso':
            discs_to_process.append(args.input)
        else:
            print(f"Error: Unsupported file type: {ext}")
            sys.exit(1)
            
        # Default output for file input
        if not args.output:
            args.output = os.path.join(os.path.dirname(args.input), "processed_fmvs")
            
    elif os.path.isdir(args.input):
        # Scan dir
        # Prefer CUEs, fallback to BINs (Track 1 only to avoid dupes)
        cues = glob.glob(os.path.join(args.input, "*.cue"))
        if cues:
            print(f"Found {len(cues)} CUE files.")
            for c in cues:
                b = parse_cue_for_bin(c)
                if b and os.path.exists(b):
                    discs_to_process.append(b)
        else:
            # Look for Track 1 bins
            bins = glob.glob(os.path.join(args.input, "*Track 1*.bin"))
            if bins:
                print(f"Found {len(bins)} BIN files (Track 1).")
                discs_to_process = bins
            else:
                 # Check for just .bin?
                 bins = glob.glob(os.path.join(args.input, "*.bin"))
                 if bins:
                     print(f"Found {len(bins)} BIN files.")
                     discs_to_process = bins

        if not args.output:
            args.output = os.path.join(args.input, "processed_fmvs")
    else:
        print(f"Error: Input not found: {args.input}")
        sys.exit(1)
        
    if not discs_to_process:
        print("No valid disc images found to process.")
        sys.exit(1)
        
    print(f"Output Directory: {args.output}")
    print(f"Discs queued: {len(discs_to_process)}")
    
    os.makedirs(args.output, exist_ok=True)
    
    for disc in discs_to_process:
        process_disc(disc, args.output)

    print("\nBatch Processing Complete!")

if __name__ == "__main__":
    main()
