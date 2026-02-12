import requests

base_url = "https://raw.githubusercontent.com/yaz0r/Azel/master/AzelLib/"
subdirs = ["audio/", "cinematics/", "kernel/", ""]

candidates = [
    "audio.cpp", "Audio.cpp", "Sound.cpp", "sound.cpp",
    "adpcm.cpp", "Adpcm.cpp", "scsp.cpp", "SCSP.cpp",
    "stream.cpp", "Stream.cpp", "cinepak.cpp", "Cinepak.cpp",
    "film.cpp", "Film.cpp", "movie.cpp", "Movie.cpp",
    "cri.cpp", "CRI.cpp", "adx.cpp", "ADX.cpp",
    "pcm.cpp", "PCM.cpp", "decode.cpp", "Decode.cpp",
    "audio_scsp.cpp", "audio_adpcm.cpp", "audio_stream.cpp",
    "audio_cinepak.cpp", "cinepak_audio.cpp"
]

def check_file(path):
    url = base_url + path
    try:
        r = requests.head(url)
        if r.status_code == 200:
            print(f"FOUND: {url}")
            return True
    except:
        pass
    return False

print("Scanning...")
found = False
for subdir in subdirs:
    for name in candidates:
        if check_file(subdir + name):
            found = True
            
if not found:
    print("No files found.")
