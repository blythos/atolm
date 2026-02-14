import os
import subprocess
import re
import sys
import glob

def get_video_duration(filepath):
    """Get video duration in seconds using FFmpeg."""
    ffmpeg_exe = os.path.abspath("tools/ffmpeg.exe")
    if not os.path.exists(ffmpeg_exe):
        ffmpeg_exe = "ffmpeg" # Fallback to PATH
        
    cmd = [ffmpeg_exe, "-i", filepath]
    try:
        result = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        # Search for "Duration: 00:00:00.00"
        match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})", result.stderr)
        if match:
            h, m, s = map(float, match.groups())
            return h * 3600 + m * 60 + s
    except Exception as e:
        print(f"Error getting duration for {filepath}: {e}")
    return 0

def get_subtitle_duration(filepath):
    """Get timestamp of last subtitle end in seconds."""
    max_time = 0
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                # 00:00:00,000 --> 00:00:00,000
                match = re.search(r"--> (\d{2}):(\d{2}):(\d{2}),(\d{3})", line)
                if match:
                    h, m, s, ms = map(int, match.groups())
                    seconds = h * 3600 + m * 60 + s + ms / 1000.0
                    if seconds > max_time:
                        max_time = seconds
    except Exception as e:
        print(f"Error parsing subtitle {filepath}: {e}")
    return max_time

def main():
    root_dir = "output/full_game_FMVs_subtitled"
    
    # Check what files exist
    print(f"Scanning {root_dir}...")
    
    mp4_files = glob.glob(os.path.join(root_dir, "**", "*.mp4"), recursive=True)
    
    print(f"{'Filename':<30} | {'Video':<10} | {'Subs':<10} | {'Diff':<10}")
    print("-" * 70)
    
    mismatches = []
    
    for mp4 in sorted(mp4_files):
        base_name = os.path.splitext(os.path.basename(mp4))[0]
        dir_name = os.path.dirname(mp4)
        
        # Subtitle usually in 'subtitles' subdir or same dir
        srt_path = os.path.join(dir_name, "subtitles", base_name + ".srt")
        if not os.path.exists(srt_path):
             srt_path = os.path.join(dir_name, base_name + ".srt")
             
        if not os.path.exists(srt_path):
             # print(f"{base_name:<30} | {'?':<10} | {'No SRT':<10} |")
             continue
             
        vid_dur = get_video_duration(mp4)
        sub_dur = get_subtitle_duration(srt_path)
        
        diff = sub_dur - vid_dur
        
        print(f"{base_name:<30} | {vid_dur:<10.2f} | {sub_dur:<10.2f} | {diff:<10.2f}")
        
        # Heuristic: If subtitles end > 5 seconds AFTER video ends, likely wrong.
        # Or if subtitles end > 30 seconds BEFORE video ends (maybe, could be long silent outro).
        # Critical mismatch: Subs significantly longer than video.
        if diff > 5.0:
            mismatches.append((base_name, diff))

    print("\nPotential Mismatches (Subs > Video + 5s):")
    for name, diff in mismatches:
        print(f"  {name}: Subs extend {diff:.2f}s past video end")

if __name__ == "__main__":
    main()
