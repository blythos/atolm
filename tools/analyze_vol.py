import subprocess
import glob

def check_vol(path):
    cmd = ['tools/ffmpeg.exe', '-i', path, '-af', 'volumedetect', '-f', 'null', '-']
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(f"--- Analysis for {path} ---")
    for line in result.stderr.split('\n'):
        if "mean_volume" in line or "max_volume" in line or "histogram" in line:
            print(line.strip())

files = glob.glob("output/disc1_v6/*.wav")
for f in files:
    check_vol(f)
