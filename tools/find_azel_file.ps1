
$baseUrl = "https://raw.githubusercontent.com/yaz0r/Azel/master/AzelLib/"
$subdirs = @("audio/", "cinematics/", "kernel/", "")
$candidates = @(
    "audio.cpp", "Audio.cpp", "Sound.cpp", "sound.cpp",
    "adpcm.cpp", "Adpcm.cpp", "scsp.cpp", "SCSP.cpp",
    "stream.cpp", "Stream.cpp", "cinepak.cpp", "Cinepak.cpp",
    "film.cpp", "Film.cpp", "movie.cpp", "Movie.cpp",
    "cri.cpp", "CRI.cpp", "adx.cpp", "ADX.cpp",
    "pcm.cpp", "PCM.cpp", "decode.cpp", "Decode.cpp",
    "audio_scsp.cpp", "audio_adpcm.cpp", "audio_stream.cpp",
    "audio_cinepak.cpp", "cinepak_audio.cpp"
)

foreach ($subdir in $subdirs) {
    foreach ($name in $candidates) {
        $url = $baseUrl + $subdir + $name
        try {
            $request = [System.Net.WebRequest]::Create($url)
            $request.Method = "HEAD"
            $response = $request.GetResponse()
            if ($response.StatusCode -eq "OK") {
                Write-Host "FOUND: $url"
                $response.Close()
                exit
            }
            $response.Close()
        } catch {
             # Ignore 404
        }
    }
}
Write-Host "No files found."
