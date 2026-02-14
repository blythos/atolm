import os
import subprocess
import argparse
import sys
import shutil

def check_ffmpeg(local_path='tools/ffmpeg.exe'):
    if shutil.which('ffmpeg'):
        return 'ffmpeg'
    if os.path.exists(local_path):
        return os.path.abspath(local_path)
    return None

def main():
    parser = argparse.ArgumentParser(description="Mux cached assets with subtitles")
    parser.add_argument('--assets', required=True, help="Directory containing .CPK and .wav files")
    parser.add_argument('--subtitles', required=True, help="Directory containing .srt files")
    parser.add_argument('--output', required=True, help="Directory to output .mp4 files")
    args = parser.parse_args()

    if not os.path.exists(args.output):
        os.makedirs(args.output)

    ffmpeg_exe = check_ffmpeg()
    if not ffmpeg_exe:
        print("Error: FFmpeg not found.")
        sys.exit(1)

    # Scan for CPKs in assets folder
    cpk_files = [f for f in os.listdir(args.assets) if f.upper().endswith('.CPK')]
    
    if not cpk_files:
        print(f"No CPK files found in {args.assets}")
        sys.exit(1)

    print(f"Found {len(cpk_files)} CPKs in assets.")

    for cpk_file in cpk_files:
        base_name = os.path.splitext(cpk_file)[0]
        cpk_path = os.path.join(args.assets, cpk_file)
        wav_path = os.path.join(args.assets, base_name + ".wav")
        srt_path = os.path.join(args.subtitles, base_name + ".srt")
        mp4_path = os.path.join(args.output, base_name + ".mp4")

        # Check if SRT exists (some CPKs might not have subs)
        has_subs = os.path.exists(srt_path)
        
        # Determine inputs
        inputs = ['-i', cpk_path]
        map_args = ['-map', '0:v']
        
        # Audio
        if os.path.exists(wav_path):
            inputs += ['-i', wav_path]
            map_args += ['-map', '1:a']
        else:
             # Fallback to internal audio if no wav found (unlikely if ripped correctly)
             map_args += ['-map', '0:a?']

        # Subtitles
        sub_args = []
        if has_subs:
            inputs += ['-i', srt_path]
            sub_idx = inputs.count('-i') - 1
            map_args += ['-map', f'{sub_idx}:s']
            sub_args = [
                '-c:s', 'mov_text',
                '-metadata:s:s:0', 'title=English',
                '-metadata:s:s:0', 'language=eng',
                '-disposition:s:0', 'default'
            ]
            print(f"Muxing {base_name} WITH subtitles...")
        else:
            print(f"Muxing {base_name} (no subtitles)...")

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
        except subprocess.CalledProcessError as e:
            print(f"Error muxing {base_name}: {e}")

    print("Muxing complete.")

if __name__ == "__main__":
    main()
