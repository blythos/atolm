"""
Panzer Dragoon Saga — Sound Test HTTP Server

Serves the browser-based sound test UI and streams extracted audio assets
(MIDI and WAV samples) to it. No game data is embedded — all assets are read
at runtime from the output/ directory produced by snd_split.py and
build_sound_catalogue.py.

Usage:
    # First build the catalogue:
    python tools/build_sound_catalogue.py --sndtest output/seq_extract/SNDTEST.PRG

    # Then start the server:
    python tools/sound_test_server.py
    python tools/sound_test_server.py --output output --port 8765

    # Open http://localhost:8765/ in your browser.

Endpoints:
    GET /                          -> redirect to /sound_test.html
    GET /sound_test.html           -> browser UI
    GET /catalogue                 -> output/sound_catalogue.json
    GET /midi/<filename>           -> MIDI file from disc1/midi/
    GET /wav/<bank>/<sample>       -> WAV file from disc1/wav/<bank>/
    GET /wav_list/<bank>           -> JSON list of WAV files in a bank dir
    GET /raw/<filename>            -> raw SEQ/BIN from disc1/raw/
"""

import io
import os
import sys
import json
import struct
import argparse
import mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, unquote

# Import SEQParser for on-the-fly conversion (no pre-generated MIDI files needed)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from seq_to_midi import SEQParser
    _SEQ_AVAILABLE = True
except ImportError:
    _SEQ_AVAILABLE = False
    print("WARNING: seq_to_midi.py not found — MIDI playback will be unavailable.")

# ---------------------------------------------------------------------------
# Configuration (overridden by CLI args)
# ---------------------------------------------------------------------------
DEFAULT_OUTPUT_DIR = 'output'
DEFAULT_PORT = 8765
DEFAULT_DISC = 'disc1'


class SoundTestHandler(BaseHTTPRequestHandler):
    """Request handler for the PDS Sound Test server."""

    # Set by SoundTestServer.make_handler()
    output_dir = DEFAULT_OUTPUT_DIR
    disc = DEFAULT_DISC
    tools_dir = os.path.dirname(os.path.abspath(__file__))

    def log_message(self, fmt, *args):
        # Suppress default noisy per-request logging; only log errors
        if args and len(args) >= 2 and str(args[1]) not in ('200', '304'):
            super().log_message(fmt, *args)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        try:
            if path in ('/', ''):
                self._redirect('/sound_test.html')
            elif path == '/sound_test.html':
                self._serve_file(os.path.join(self.tools_dir, 'sound_test.html'), 'text/html')
            elif path == '/catalogue':
                self._serve_json(os.path.join(self.output_dir, 'sound_catalogue.json'))
            elif path.startswith('/midi/'):
                fname = path[len('/midi/'):]
                self._serve_midi_dynamic(fname)
            elif path.startswith('/sf2/'):
                fname = path[len('/sf2/'):]
                self._serve_file(
                    os.path.join(self.output_dir, 'sf2', fname),
                    'application/octet-stream'
                )
            elif path.startswith('/wav_list/'):
                bank = path[len('/wav_list/'):]
                self._serve_wav_list(bank)
            elif path.startswith('/wav_map/'):
                bank = path[len('/wav_map/'):]
                self._serve_wav_map(bank)
            elif path.startswith('/wav/'):
                # /wav/<bank>/<sample.wav>
                parts = path[len('/wav/'):].split('/', 1)
                if len(parts) == 2:
                    bank, sample = parts
                    self._serve_file(
                        os.path.join(self.output_dir, 'snd_split', self.disc, 'wav', bank, sample),
                        'audio/wav'
                    )
                else:
                    self._404()
            elif path.startswith('/raw/'):
                fname = path[len('/raw/'):]
                self._serve_file(
                    os.path.join(self.output_dir, 'snd_split', self.disc, 'raw', fname),
                    'application/octet-stream'
                )
            else:
                self._404()
        except Exception as e:
            self._error(500, str(e))

    def _serve_midi_dynamic(self, fname):
        """Convert a raw .SEQ file to MIDI on the fly and stream the result."""
        if not _SEQ_AVAILABLE:
            self._error(503, 'seq_to_midi.py not available — cannot generate MIDI')
            return

        # Strip .mid extension if present; look for matching .SEQ file
        stem = fname
        for ext in ('.mid', '.midi', '.MID', '.MIDI'):
            if stem.endswith(ext):
                stem = stem[:-len(ext)]
                break

        # Try both uppercase and original case (disc files are uppercase)
        raw_dir = os.path.join(self.output_dir, 'snd_split', self.disc, 'raw')
        seq_path = None
        for candidate in [stem + '.SEQ', stem.upper() + '.SEQ', stem.lower() + '.seq']:
            p = os.path.join(raw_dir, candidate)
            if os.path.isfile(p):
                seq_path = p
                break

        if seq_path is None:
            self._404(f'SEQ file not found for: {fname}')
            return

        try:
            with open(seq_path, 'rb') as f:
                data = f.read()

            # SEQ multi-song layout: u16 num_songs + num_songs × u32 absolute song offsets.
            # Each u32 pointer is 4 bytes big-endian. The old code read only 3 bytes,
            # which always produced ptr=0, making resolution=num_songs (1, 2, 3...) instead
            # of the actual value (48, 480, 384, etc.) — all notes played in near-zero time.
            num_songs = struct.unpack('>H', data[0:2])[0]
            if 0 < num_songs < 256:
                ptr = struct.unpack('>I', data[2:6])[0]  # 4-byte u32, not 3-byte
                ptr = ptr if ptr < len(data) else 0
            else:
                ptr = 0

            parser = SEQParser(data)
            parser.song_start_offset = ptr
            parser.parse_header(ptr)
            mid = parser.convert_to_midi(stem)

            buf = io.BytesIO()
            mid.save(file=buf)
            midi_bytes = buf.getvalue()

        except Exception as e:
            self._error(500, f'SEQ conversion failed: {e}')
            return

        self.send_response(200)
        self.send_header('Content-Type', 'audio/midi')
        self.send_header('Content-Length', str(len(midi_bytes)))
        self._cors()
        self.end_headers()
        self.wfile.write(midi_bytes)

    def _redirect(self, location):
        self.send_response(302)
        self.send_header('Location', location)
        self._cors()
        self.end_headers()

    def _serve_file(self, filepath, content_type=None):
        if not os.path.isfile(filepath):
            self._404(filepath)
            return
        size = os.path.getsize(filepath)
        if content_type is None:
            content_type, _ = mimetypes.guess_type(filepath)
            content_type = content_type or 'application/octet-stream'
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(size))
        self._cors()
        self.end_headers()
        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def _serve_json(self, filepath):
        if not os.path.isfile(filepath):
            self._404(filepath)
            return
        with open(filepath, 'r', encoding='utf-8') as f:
            data = f.read()
        encoded = data.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self._cors()
        self.end_headers()
        self.wfile.write(encoded)

    def _serve_wav_list(self, bank):
        """Return JSON list of WAV filenames in a tone bank directory."""
        wav_dir = os.path.join(self.output_dir, 'snd_split', self.disc, 'wav', bank)
        if not os.path.isdir(wav_dir):
            files = []
        else:
            files = sorted(f for f in os.listdir(wav_dir) if f.lower().endswith('.wav'))
        body = json.dumps(files).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _serve_wav_map(self, bank):
        """Return JSON mapping voice_index -> list of {wav, root} for a tone bank.

        Parses the BIN file to get the correct voice->sample ordering and ALL layers.
        Each voice index corresponds to MIDI program N. Multi-layer voices return all
        layers so the browser can feed them all into a single Tone.Sampler for correct
        key-split playback (low notes from one sample, high notes from another).

        Response: { "3": [{"wav": "sample_005.wav", "root": 37},
                           {"wav": "sample_009.wav", "root": 80},
                           {"wav": "sample_006.wav", "root": 47}], ... }
        Falls back to sorted alphabetical order with root=60 if BIN is unavailable.
        """
        raw_dir = os.path.join(self.output_dir, 'snd_split', self.disc, 'raw')
        wav_dir = os.path.join(self.output_dir, 'snd_split', self.disc, 'wav', bank)

        # Collect available WAV files and index by their encoded byte offset
        if not os.path.isdir(wav_dir):
            self._serve_json_obj({})
            return

        wav_files = sorted(f for f in os.listdir(wav_dir) if f.lower().endswith('.wav'))
        off_to_wav = {}
        for w in wav_files:
            # Filename encodes offset: sample_NNN_at0xHEX_...
            for part in w.split('_'):
                if part.startswith('at0x'):
                    try:
                        off = int(part[2:], 16)
                        off_to_wav[off] = w
                    except ValueError:
                        pass
                    break

        # Try to find the matching BIN file
        bin_path = None
        for candidate in [bank + '.BIN', bank.upper() + '.BIN']:
            p = os.path.join(raw_dir, candidate)
            if os.path.isfile(p):
                bin_path = p
                break

        voice_map = {}  # str(voice_idx) -> list of { "wav": filename, "root": midi_note }

        if bin_path:
            try:
                with open(bin_path, 'rb') as f:
                    data = f.read()

                # Header: 4 x u16 section offsets
                mixer_off, vl_off, peg_off, plfo_off = struct.unpack_from('>HHHH', data, 0)
                num_voices = (mixer_off - 8) // 2

                # Voice descriptors start at plfo_off + 4
                vp = plfo_off + 4
                for vi in range(num_voices):
                    if vp + 4 > len(data):
                        break
                    hdr = data[vp:vp + 4]
                    nlayers = hdr[2] + 1   # byte[2] = nlayers - 1
                    vp += 4
                    if nlayers < 1 or nlayers > 64:
                        break  # sanity check

                    layers = []
                    for li in range(nlayers):
                        lb = vp + li * 32
                        if lb + 32 > len(data):
                            break

                        raw_u32 = struct.unpack_from('>I', data, lb + 2)[0]
                        tone_off = raw_u32 & 0x0007FFFF
                        wav = off_to_wav.get(tone_off)
                        if not wav:
                            continue

                        lo_key = data[lb + 0]
                        hi_key = data[lb + 1]
                        if lo_key == 0 and hi_key == 127:
                            # Full-range layer: no defined root, default C4=60
                            root = 60
                        elif lo_key == hi_key:
                            # Single-note layer: lo_key IS the exact root
                            root = lo_key
                        else:
                            # Narrow range: midpoint as approximation
                            root = (lo_key + hi_key) // 2

                        layers.append({"wav": wav, "root": root})

                    if layers:
                        voice_map[str(vi)] = layers

                    vp += nlayers * 32
            except Exception:
                pass  # fall through to alphabetical fallback

        if not voice_map:
            # Fallback: map voice index i -> sorted WAV file i, root=60
            for i, w in enumerate(wav_files):
                voice_map[str(i)] = [{"wav": w, "root": 60}]

        self._serve_json_obj(voice_map)

    def _serve_json_obj(self, obj):
        """Serialise a Python object to JSON and send it."""
        body = json.dumps(obj).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')

    def _404(self, path=''):
        msg = f'Not found: {path}'.encode('utf-8')
        self.send_response(404)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', str(len(msg)))
        self._cors()
        self.end_headers()
        self.wfile.write(msg)

    def _error(self, code, msg):
        body = msg.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)


# ---------------------------------------------------------------------------
# Server startup
# ---------------------------------------------------------------------------

def check_prerequisites(output_dir, disc):
    """Warn about missing outputs but don't abort — partial data is still useful."""
    ok = True
    catalogue = os.path.join(output_dir, 'sound_catalogue.json')
    raw_dir   = os.path.join(output_dir, 'snd_split', disc, 'raw')
    wav_dir   = os.path.join(output_dir, 'snd_split', disc, 'wav')

    if not os.path.exists(catalogue):
        print(f"  WARNING: sound_catalogue.json not found at {catalogue}")
        print(f"  Run: python tools/build_sound_catalogue.py --sndtest output/seq_extract/SNDTEST.PRG")
        ok = False
    else:
        with open(catalogue) as f:
            cat = json.load(f)
        stats = cat.get('stats', {})
        print(f"  Catalogue: {stats.get('named_matched', '?')} named tracks, "
              f"{stats.get('extra_seq_files', '?')} extra, "
              f"{stats.get('total_seq_files', '?')} total SEQ files")

    # MIDI is generated on the fly from raw SEQ files — check for those instead
    seq_count = len([f for f in os.listdir(raw_dir) if f.upper().endswith('.SEQ')]) \
                if os.path.isdir(raw_dir) else 0
    wav_count = len(os.listdir(wav_dir)) if os.path.isdir(wav_dir) else 0

    if seq_count == 0:
        print(f"  WARNING: No SEQ files found in {raw_dir}")
        print(f"  Run: python tools/snd_split.py --extract --disc1 <iso>")
        ok = False
    else:
        print(f"  SEQ files: {seq_count} (MIDI generated on the fly)")

    if not _SEQ_AVAILABLE:
        print(f"  WARNING: seq_to_midi.py not importable — MIDI playback disabled")
        ok = False

    if wav_count == 0:
        print(f"  WARNING: No WAV banks found in {wav_dir}")
        print(f"  Run: python tools/snd_split.py --extract --disc1 <iso>")
        ok = False
    else:
        print(f"  WAV banks: {wav_count} directories")

    return ok


def main():
    parser = argparse.ArgumentParser(
        description='PDS Sound Test HTTP Server',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--output', metavar='DIR', default=DEFAULT_OUTPUT_DIR,
                        help=f'Output directory containing sound_catalogue.json and snd_split/ '
                             f'(default: {DEFAULT_OUTPUT_DIR})')
    parser.add_argument('--disc', metavar='LABEL', default=DEFAULT_DISC,
                        help=f'Disc label subdirectory under snd_split/ (default: {DEFAULT_DISC})')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT,
                        help=f'HTTP port to listen on (default: {DEFAULT_PORT})')
    args = parser.parse_args()

    output_dir = os.path.abspath(args.output)

    print("PDS Sound Test Server")
    print(f"  Output dir: {output_dir}")
    print(f"  Disc:       {args.disc}")
    print()
    print("Checking prerequisites...")
    check_prerequisites(output_dir, args.disc)
    print()

    # Build handler class with config baked in
    handler = type('Handler', (SoundTestHandler,), {
        'output_dir': output_dir,
        'disc':       args.disc,
        'tools_dir':  os.path.dirname(os.path.abspath(__file__)),
    })

    server = HTTPServer(('localhost', args.port), handler)
    print(f"Listening on http://localhost:{args.port}/")
    print("Open that URL in your browser to start the sound test.")
    print("Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == '__main__':
    main()
