"""
Panzer Dragoon Saga — Dragon Morpher HTTP Server

Serves the browser-based dragon morphing tool. Reads raw MCB/CGB data and
structure JSONs from the output/raw/ directory (produced by pds_extract_raw.py).

Usage:
    python tools/dragon_morpher_server.py [--output output] [--port 8770]
    Open: http://localhost:8770/
"""

import os
import sys
import json
import argparse
import mimetypes
from http.server import HTTPServer, SimpleHTTPRequestHandler

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEFAULT_OUTPUT_DIR = 'output'
DEFAULT_PORT = 8770

# Dragon level definitions (from dragonData.cpp / common.h)
DRAGON_LEVELS = [
    {"level": 0, "name": "Basic Wing",   "base": "DRAGON0", "morph": None,       "combat": "DRAGONC0", "morphable": False},
    {"level": 1, "name": "Valiant Wing", "base": "DRAGON1", "morph": "DRAGONM1", "combat": "DRAGONC1", "morphable": True},
    {"level": 2, "name": "Stripe Wing",  "base": "DRAGON2", "morph": "DRAGONM2", "combat": "DRAGONC2", "morphable": True},
    {"level": 3, "name": "Panzer Wing",  "base": "DRAGON3", "morph": "DRAGONM3", "combat": "DRAGONC3", "morphable": True},
    {"level": 4, "name": "Eye Wing",     "base": "DRAGON4", "morph": "DRAGONM4", "combat": "DRAGONC4", "morphable": True},
    {"level": 5, "name": "Arm Wing",     "base": "DRAGON5", "morph": "DRAGONM5", "combat": None,       "morphable": True},
    {"level": 6, "name": "Light Wing",   "base": "DRAGON6", "morph": None,       "combat": None,       "morphable": False},
    {"level": 7, "name": "Solo Wing",    "base": "DRAGON7", "morph": "DRAGONM7", "combat": None,       "morphable": True},
    {"level": 8, "name": "Floater",      "base": "KTEI",    "morph": None,       "combat": None,       "morphable": False},
]


class DragonMorpherHandler(SimpleHTTPRequestHandler):
    """Request handler for the Dragon Morpher server."""

    output_dir = DEFAULT_OUTPUT_DIR
    tools_dir = os.path.dirname(os.path.abspath(__file__))

    def log_message(self, fmt, *args):
        # Quieter logging
        if '/api/' in str(args[0]) if args else False:
            return
        super().log_message(fmt, *args)

    def do_GET(self):
        path = self.path.split('?')[0]

        # ── API Endpoints ──────────────────────────────────────────────
        if path == '/api/dragons':
            return self._serve_dragon_list()

        if path.startswith('/api/raw/'):
            # Serve raw MCB/CGB/structure files
            fname = path[len('/api/raw/'):]
            return self._serve_raw_file(fname)

        # ── Static Files ───────────────────────────────────────────────
        if path == '/' or path == '/index.html':
            return self._serve_file(
                os.path.join(self.tools_dir, 'dragon_morpher.html'),
                'text/html')

        if path == '/viewer_renderer.js':
            return self._serve_file(
                os.path.join(self.tools_dir, 'viewer_renderer.js'),
                'application/javascript')

        if path == '/viewer_animation.js':
            return self._serve_file(
                os.path.join(self.tools_dir, 'viewer_animation.js'),
                'application/javascript')

        return self._404(path)

    # ── API Handlers ───────────────────────────────────────────────────

    def _serve_dragon_list(self):
        """Return dragon level config + file availability."""
        raw_dir = os.path.join(self.output_dir, 'raw')
        result = []
        for d in DRAGON_LEVELS:
            entry = dict(d)
            # Check file availability
            base_mcb = os.path.join(raw_dir, f"{d['base']}.mcb.bin")
            entry['baseAvailable'] = os.path.isfile(base_mcb)
            if d['morph']:
                morph_mcb = os.path.join(raw_dir, f"{d['morph']}.mcb.bin")
                entry['morphAvailable'] = os.path.isfile(morph_mcb)
            else:
                entry['morphAvailable'] = False
            result.append(entry)
        self._serve_json_obj(result)

    def _serve_raw_file(self, fname):
        """Serve a file from output/raw/."""
        # Security: only allow specific extensions
        if not any(fname.endswith(ext) for ext in
                   ['.mcb.bin', '.cgb.bin', '_structure.json']):
            return self._404(fname)
        filepath = os.path.join(self.output_dir, 'raw', fname)
        if not os.path.isfile(filepath):
            return self._404(fname)
        content_type = 'application/octet-stream'
        if fname.endswith('.json'):
            content_type = 'application/json'
        self._serve_file(filepath, content_type)

    # ── Helpers ────────────────────────────────────────────────────────

    def _serve_file(self, filepath, content_type=None):
        if not os.path.isfile(filepath):
            return self._404(filepath)
        if content_type is None:
            content_type, _ = mimetypes.guess_type(filepath)
            content_type = content_type or 'application/octet-stream'
        with open(filepath, 'rb') as f:
            data = f.read()
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def _serve_json_obj(self, obj):
        data = json.dumps(obj, indent=2).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')

    def _404(self, path=''):
        msg = f'Not found: {path}'.encode('utf-8')
        self.send_response(404)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', str(len(msg)))
        self.end_headers()
        self.wfile.write(msg)


# ---------------------------------------------------------------------------
# Server startup
# ---------------------------------------------------------------------------

def check_prerequisites(output_dir):
    """Check that required data directories exist."""
    raw_dir = os.path.join(output_dir, 'raw')
    if not os.path.isdir(raw_dir):
        print(f"WARNING: Raw data directory not found: {raw_dir}")
        print("  Run pds_extract_raw.py first to extract MCB/CGB data.")
        return False

    # Check for at least one dragon
    dragon0 = os.path.join(raw_dir, 'DRAGON0.mcb.bin')
    if not os.path.isfile(dragon0):
        print(f"WARNING: DRAGON0.mcb.bin not found in {raw_dir}")
        print("  Dragon models may not have been extracted yet.")
        return False

    # Count available dragons
    available = 0
    for d in DRAGON_LEVELS:
        mcb = os.path.join(raw_dir, f"{d['base']}.mcb.bin")
        if os.path.isfile(mcb):
            available += 1
    print(f"  Found {available}/{len(DRAGON_LEVELS)} dragon base models")
    return True


def main():
    parser = argparse.ArgumentParser(
        description='PDS Dragon Morpher Server')
    parser.add_argument('--output', default=DEFAULT_OUTPUT_DIR,
                        help=f'Output directory (default: {DEFAULT_OUTPUT_DIR})')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT,
                        help=f'HTTP port (default: {DEFAULT_PORT})')
    args = parser.parse_args()

    output_dir = os.path.abspath(args.output)
    print(f"PDS Dragon Morpher Server")
    print(f"  Output dir: {output_dir}")

    check_prerequisites(output_dir)

    DragonMorpherHandler.output_dir = output_dir

    server = HTTPServer(('', args.port), DragonMorpherHandler)
    print(f"\n  Listening on http://localhost:{args.port}/")
    print(f"  Press Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == '__main__':
    main()
