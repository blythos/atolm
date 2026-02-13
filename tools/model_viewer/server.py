import http.server
import json
import os
import struct
import argparse
import sys
import io

# Add project root to sys.path to import common modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from tools.common.iso9660 import ISO9660Reader
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Constants
MCB_EXTENSION = '.MCB'
CGB_EXTENSION = '.CGB'

class ModelViewerHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.path = '/tools/model_viewer/index.html'
            return http.server.SimpleHTTPRequestHandler.do_GET(self)
        
        if self.path.startswith('/api/assets'):
            self.handle_api_assets()
        elif self.path.startswith('/api/model/'):
            model_name = self.path.split('/')[-1]
            self.handle_api_model(model_name)
        elif self.path.startswith('/api/texture/'):
            parts = self.path.split('/')
            if len(parts) >= 4:
                model_name = parts[3]
                texture_index = int(parts[4].split('.')[0])
                self.handle_api_texture(model_name, texture_index)
            else:
                self.send_error(400, "Invalid texture request")
        else:
            # Fallback to serving static files from project root to allow access to tools/model_viewer/index.html
            # But SimpleHTTPRequestHandler serves from CWD by default.
            # If we run from project root, path /tools/model_viewer/index.html works.
            return http.server.SimpleHTTPRequestHandler.do_GET(self)

    def handle_api_assets(self):
        assets = self.server.iso_reader.list_files()
        mcb_files = [f for f in assets if f['name'].endswith(MCB_EXTENSION)]
        
        grouped_assets = {}
        for f in mcb_files:
            name = f['name']
            category = self.categorize_asset(name)
            if category not in grouped_assets:
                grouped_assets[category] = []
            
            # Find matching CGB
            base_name = name[:-4]
            cgb_name = base_name + CGB_EXTENSION
            has_cgb = any(a['name'] == cgb_name for a in assets)
            
            grouped_assets[category].append({
                'name': base_name,
                'size': f['size'],
                'has_cgb': has_cgb
            })
            
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(grouped_assets).encode('utf-8'))

    def categorize_asset(self, name):
        if name.startswith('DRAGON'): return 'Dragons'
        if name.startswith('EDGE') or name.startswith('AZEL'): return 'Characters'
        if name.startswith('X_') or name.startswith('Z_'): return 'NPCs'
        if name.startswith('FLD_'): return 'Fields'
        if 'MP' in name: return 'Maps'
        return 'Other'


    def handle_api_model(self, name):
        mcb_file = self.find_file(name + MCB_EXTENSION)
        if not mcb_file:
            self.send_error(404, "Model not found")
            return

        print(f"Parsing model {name}...")
        try:
            mcb_data = self.server.iso_reader.extract_file(mcb_file['lba'], mcb_file['size'])
            model_data = self.parse_mcb(mcb_data)
            
            # Check for CGB
            cgb_file = self.find_file(name + CGB_EXTENSION)
            model_data['has_textures'] = bool(cgb_file)

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(model_data).encode('utf-8'))
        except Exception as e:
            print(f"Error parsing model {name}: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Error parsing model: {str(e)}")

    def handle_api_texture(self, name, index):
        # 1. Re-parse MCB to identify texture params
        # This is inefficient but avoids caching complexity
        mcb_file = self.find_file(name + MCB_EXTENSION)
        if not mcb_file:
            self.send_error(404, "Model not found")
            return
            
        try:
            mcb_data = self.server.iso_reader.extract_file(mcb_file['lba'], mcb_file['size'])
            model_data = self.parse_mcb(mcb_data)
            textures = model_data.get('textures', [])
            
            if index < 0 or index >= len(textures):
                self.send_error(404, "Texture index out of range")
                return
                
            tex_params = textures[index]
            
            # 2. Load CGB
            cgb_file = self.find_file(name + CGB_EXTENSION)
            if not cgb_file:
                # Generate a dummy placeholder or error?
                # Task implies CGB exists if textures requested.
                self.send_error(404, "CGB file not found")
                return

            cgb_data = self.server.iso_reader.extract_file(cgb_file['lba'], cgb_file['size'])
            
            # 3. Convert
            png_data = self.convert_texture(cgb_data, tex_params)
            
            self.send_response(200)
            self.send_header('Content-type', 'image/png')
            self.end_headers()
            self.wfile.write(png_data)
            
        except Exception as e:
            print(f"Error serving texture {name}/{index}: {e}")
            traceback.print_exc()
            self.send_error(500, f"Texture error: {e}")

    def convert_texture(self, cgb_data, params):
        srca = params['srca']
        colr = params['colr']
        size = params['size']
        pmod = params['pmod']  # (CMDPMOD >> 3) & 7 from parser
        
        # Decode size
        # Width = (CMDSIZE & 0x3F00) >> 5
        # Height = CMDSIZE & 0xFF
        # Note: Width is "width / 8" stored in bits 8-13? 
        # Task: "CMDSIZE (bits 8-13: width÷8 → shift right 5; bits 0-7: height)"
        # So: width = ((size & 0x3F00) >> 8) * 8 ?
        # Task says: "(CMDSIZE & 0x3F00) >> 5". 
        # Let's check logic: (0x3F00 >> 8) is value 0-63. Multiplied by 8.
        # (0x3F00 >> 5) is equivalent to (0x3F00 >> 8) << 3. Yes.
        
        width = (size & 0x3F00) >> 5
        height = size & 0x00FF
        
        if width == 0 or height == 0:
            return self.create_placeholder_png(16, 16, (255, 0, 255))
            
        # Texture offset = CMDSRCA * 8
        tex_offset = srca * 8
        
        img = Image.new('RGB', (width, height), (0, 0, 0))
        pixels = img.load()
        
        mode = (pmod >> 3) & 7
        
        try:
            if mode == 1: # 4bpp LUT
                # Palette offset = CMDCOLR * 8
                pal_offset = colr * 8
                # Read 16 colors (16 * 2 bytes = 32 bytes)
                palette = []
                for i in range(16):
                    off = pal_offset + i * 2
                    if off + 2 > len(cgb_data):
                        palette.append((0,0,0))
                        continue
                    val = struct.unpack('>H', cgb_data[off:off+2])[0]
                    palette.append(self.decode_rgb555(val))
                
                # Read pixels
                # 4bpp = 2 pixels per byte
                # Stride? Usually linear.
                current_off = tex_offset
                for y in range(height):
                    for x in range(0, width, 2):
                        if current_off >= len(cgb_data): break
                        b = cgb_data[current_off]
                        current_off += 1
                        
                        # High nibble first? Saturn VDP1 usually High=First Pixel, Low=Second Pixel?
                        # Or Low=First?
                        # VDP1 standard: 4bpp packed.
                        # Usually: (b >> 4) is pixel x, (b & 0xF) is pixel x+1
                        p1 = (b >> 4) & 0xF
                        p2 = b & 0xF
                        
                        pixels[x, y] = palette[p1]
                        if x + 1 < width:
                             pixels[x+1, y] = palette[p2]

            elif mode == 5: # 16bpp RGB555
                current_off = tex_offset
                for y in range(height):
                    for x in range(width):
                        if current_off + 2 > len(cgb_data): break
                        val = struct.unpack('>H', cgb_data[current_off:current_off+2])[0]
                        current_off += 2
                        pixels[x, y] = self.decode_rgb555(val)
            
            else:
                # Mode 0 (grayscale) or others
                # Render cheap placeholder
                return self.create_placeholder_png(width, height, (100, 100, 100))

        except Exception as e:
            print(f"Error converting texture: {e}")
            return self.create_placeholder_png(width, height, (255, 0, 0))

        # Save to buffer
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()

    def decode_rgb555(self, val):
        # MSB is usually transparency bit in VDP1, but for textures it might be ignored or used.
        # Task says: "R=bits 0-4, G=bits 5-9, B=bits 10-14" (Little Endian view? No, bits are usually LSB 0)
        # Saturn is Big Endian, but bit packing is:
        # 1 1111 1111 1111 11
        # | B    G    R
        # Wait, Task says: "R=bits 0-4, G=bits 5-9, B=bits 10-14"
        # This means 0x7C00 is Blue, 0x03E0 is Green, 0x001F is Red.
        
        r = (val & 0x001F) << 3
        g = ((val & 0x03E0) >> 5) << 3
        b = ((val & 0x7C00) >> 10) << 3
        
        # Expand range 0-248 to 0-255?
        # Usually | (val >> 2) but simple shift is fine for now
        return (r, g, b)

    def create_placeholder_png(self, w, h, color):
        img = Image.new('RGB', (w, h), color)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()

    def find_file(self, filename):
        files = self.server.iso_reader.list_files()
        return next((f for f in files if f['name'] == filename), None)

    def parse_mcb(self, data):
        # ... (Previous pointer table parsing code)
        pointers = []
        offset = 0
        while offset < len(data):
            val = struct.unpack('>I', data[offset:offset+4])[0]
            if offset > 0 and val == pointers[0]: break
            if len(pointers) > 0 and offset >= pointers[0]: break
            pointers.append(val)
            offset += 4
            
        models = []
        print(f"DEBUG: Found {len(pointers)} pointers: {pointers[:10]}...")
        
        for i, p_offset in enumerate(pointers):
            if p_offset == 0 or p_offset >= len(data): continue
            
            # Check what this chunk is
            if p_offset + 32 < len(data): # Header analysis (8 words)
                H = struct.unpack('>8I', data[p_offset:p_offset+32])
                v0, v4, v8, v12, v16 = H[0], H[1], H[2], H[3], H[4]
                
                # print(f"DEBUG: Chunk at {p_offset:X}: {v0:X} {v4:X} {v8:X} {v12:X} {v16:X}")
                
                # Dynamic Heuristic for v4/v8 (Offset vs Count)
                # v4 is traditionally VtxCount, v8 is PolyOffset.
                # But sometimes they seem swapped or different.
                # We expect Offset > 64 (header size) and Count < 10000.
                
                vtx_count = 0
                poly_off = 0
                
                # Case A: Standard (v4=Count, v8=Offset)
                if v4 < 10000 and v8 > 64 and v8 < len(data):
                    vtx_count = v4
                    poly_off = v8
                    print(f"DEBUG: Chunk {p_offset:X} Case A: v4=Cnt({v4}), v8=Off({v8:X})", flush=True)
                # Case B: Swapped (v4=Offset, v8=Count)
                elif v8 < 10000 and v4 > 64 and v4 < len(data):
                    vtx_count = v8
                    poly_off = v4
                    print(f"DEBUG: Chunk {p_offset:X} Case B: v4=Off({v4:X}), v8=Cnt({v8})", flush=True)
                else:
                    # Fallback or invalid
                    print(f"DEBUG: Chunk {p_offset:X} Unrecognized. v4={v4:X} v8={v8:X}", flush=True)
                
                poly_count = v12 & 0xFFFF
                print(f"DEBUG: Chunk {p_offset:X} Raw v12: {v12:X} PolyCount: {poly_count}", flush=True)
                
                if vtx_count > 0 and poly_count >= 0:
                    vtx_off_candidate = 0
                    if v0 < len(data) and (v0 % 2) == 0 and v0 > 64: vtx_off_candidate = v0
                    elif v16 < len(data) and (v16 % 2) == 0 and v16 > 64 and H[4] != 0: vtx_off_candidate = v16
                    
                    print(f"DEBUG: Model? at {p_offset:X}. Vtx:{vtx_count} Poly:{poly_count}. PolyOff:{poly_off:X} VtxOff:{vtx_off_candidate:X}", flush=True)
                    
                    # Strict validation
                    if vtx_off_candidate != 0 and poly_off != 0:
                        try:
                            model = self.parse_single_model_patched(data, p_offset, vtx_off_candidate, poly_off, vtx_count, poly_count)
                            models.append(model)
                            print(f"DEBUG: Successfully parsed chunk at {p_offset:X}", flush=True)
                            continue
                        except Exception as e:
                            print(f"DEBUG: Failed to parse chunk at {p_offset:X}: {e}", flush=True)
                            import traceback; traceback.print_exc()
                    else:
                        print(f"DEBUG: Skipped chunk at {p_offset:X} due to invalid offsets.", flush=True)

        final_model = { 'name': 'Model', 'groups': {'default': {'positions':[], 'uvs':[], 'texture_index': -1}}, 'textures': [] }
        if models:
            # We assume single model for now or merge
            # But parse_single_model now should return groups with texture parameters.
            # We need to consolidate the textures into a list and assign indices.
            
            raw_groups = models[0]['groups'] # map of tex_key -> {texture_params, positions, uvs}
            
            texture_list = []
            final_groups = {} # index -> geometry
            
            # Sort keys to ensure deterministic order (for index stability)
            sorted_keys = sorted(raw_groups.keys())
            
            for i, key in enumerate(sorted_keys):
                group = raw_groups[key]
                texture_list.append(group['texture_params'])
                
                final_groups[str(i)] = {
                    'positions': group['positions'],
                    'uvs': group['uvs'],
                    'texture_index': i
                }
            
            final_model = {
                'name': 'Model',
                'groups': final_groups,
                'textures': texture_list
            }
            
        return final_model

    def parse_single_model_patched(self, data, offset, vertex_offset, polygon_offset, curr_vtx_count, curr_poly_count):
        # Override the offsets reading
        # ... logic similar to before but using passed values
        
        # Read Vertices
        vertices = []
        v_off = vertex_offset
        print(f"DEBUG: parse_single_model_patched len(data)={len(data)} v_off={v_off} count={curr_vtx_count}", flush=True)
        for _ in range(curr_vtx_count):
            if v_off + 6 > len(data): break
            vx = struct.unpack('>h', data[v_off:v_off+2])[0] / 256.0
            vy = struct.unpack('>h', data[v_off+2:v_off+4])[0] / 256.0
            vz = struct.unpack('>h', data[v_off+4:v_off+6])[0] / 256.0
            v_off += 6
            vertices.append(vx); vertices.append(-vy); vertices.append(vz)

        print(f"DEBUG: Chunk {offset:X} Parsed {len(vertices)//3} vertices (Expected {curr_vtx_count})", flush=True)

        faces_by_texture = {} 
        
        p_off = polygon_offset
        print(f"DEBUG: Reading polys at {p_off:X}. Data around {p_off:X}: {data[p_off:p_off+128].hex()}", flush=True)
        
        for _ in range(curr_poly_count):
            if p_off + 20 > len(data): break
            indices = struct.unpack('>4H', data[p_off:p_off+8])
            print(f"DEBUG: Poly Indices: {indices}", flush=True)
            p_off += 8
            
            lighting = struct.unpack('>H', data[p_off:p_off+2])[0]
            cmdctrl = struct.unpack('>H', data[p_off+2:p_off+4])[0]
            cmdpmod = struct.unpack('>H', data[p_off+4:p_off+6])[0]
            cmdcolr = struct.unpack('>H', data[p_off+6:p_off+8])[0]
            cmdsrca = struct.unpack('>H', data[p_off+8:p_off+10])[0]
            cmdsize = struct.unpack('>H', data[p_off+10:p_off+12])[0]
            p_off += 12
            
            mode = (lighting >> 8) & 0x03
            if mode == 1: p_off += 8
            elif mode == 2: p_off += 48
            elif mode == 3: p_off += 24
            
            tex_params = { 'srca': cmdsrca, 'colr': cmdcolr, 'size': cmdsize, 'pmod': cmdpmod }
            tex_key = f"{cmdsrca}_{cmdcolr}_{cmdsize}_{cmdpmod}"
            
            if tex_key not in faces_by_texture:
                faces_by_texture[tex_key] = {
                    'texture_params': tex_params,
                    'positions': [],
                    'uvs': []
                }
                
            h_flip = (cmdctrl & 0x0010) != 0
            v_flip = (cmdctrl & 0x0020) != 0
            base_uvs = [[0,0], [1,0], [1,1], [0,1]]
            if h_flip:
                 for uv in base_uvs: uv[0] = 1 - uv[0]
            if v_flip:
                 for uv in base_uvs: uv[1] = 1 - uv[1]
            
            try:
                self.add_tri(faces_by_texture[tex_key], vertices, [indices[0], indices[1], indices[2]], [base_uvs[0], base_uvs[1], base_uvs[2]])
                if indices[2] != indices[3]:
                    self.add_tri(faces_by_texture[tex_key], vertices, [indices[0], indices[2], indices[3]], [base_uvs[0], base_uvs[2], base_uvs[3]])
            except IndexError:
                # print(f"DEBUG: Skipping poly with invalid indices: {indices}", flush=True)
                pass
                
        return { 'name': 'Model', 'groups': faces_by_texture }

    def parse_single_model(self, data, offset):
        obj_start = offset
        vertex_offset = struct.unpack('>I', data[obj_start:obj_start+4])[0]
        curr_vtx_count = struct.unpack('>I', data[obj_start+4:obj_start+8])[0]
        polygon_offset = struct.unpack('>I', data[obj_start+8:obj_start+12])[0]
        curr_poly_count = struct.unpack('>I', data[obj_start+12:obj_start+16])[0]

        vertices = []
        v_off = vertex_offset
        for _ in range(curr_vtx_count):
            vx = struct.unpack('>h', data[v_off:v_off+2])[0] / 256.0
            vy = struct.unpack('>h', data[v_off+2:v_off+4])[0] / 256.0
            vz = struct.unpack('>h', data[v_off+4:v_off+6])[0] / 256.0
            v_off += 6
            vertices.append(vx); vertices.append(-vy); vertices.append(vz) # Try standard Z

        faces_by_texture = {} # Key: specific params string
        
        p_off = polygon_offset
        for _ in range(curr_poly_count):
            indices = struct.unpack('>4H', data[p_off:p_off+8])
            p_off += 8
            
            lighting = struct.unpack('>H', data[p_off:p_off+2])[0]
            cmdctrl = struct.unpack('>H', data[p_off+2:p_off+4])[0]
            cmdpmod = struct.unpack('>H', data[p_off+4:p_off+6])[0]
            cmdcolr = struct.unpack('>H', data[p_off+6:p_off+8])[0]
            cmdsrca = struct.unpack('>H', data[p_off+8:p_off+10])[0]
            cmdsize = struct.unpack('>H', data[p_off+10:p_off+12])[0]
            p_off += 12
            
            mode = (lighting >> 8) & 0x03
            if mode == 1: p_off += 8
            elif mode == 2: p_off += 48
            elif mode == 3: p_off += 24
            
            tex_params = { 'srca': cmdsrca, 'colr': cmdcolr, 'size': cmdsize, 'pmod': cmdpmod }
            # Create a unique key for grouping
            tex_key = f"{cmdsrca}_{cmdcolr}_{cmdsize}_{cmdpmod}"
            
            if tex_key not in faces_by_texture:
                faces_by_texture[tex_key] = {
                    'texture_params': tex_params,
                    'positions': [],
                    'uvs': []
                }
                
            h_flip = (cmdctrl & 0x0010) != 0
            v_flip = (cmdctrl & 0x0020) != 0
            base_uvs = [[0,0], [1,0], [1,1], [0,1]]
            if h_flip:
                 for uv in base_uvs: uv[0] = 1 - uv[0]
            if v_flip:
                 for uv in base_uvs: uv[1] = 1 - uv[1]
            
            self.add_tri(faces_by_texture[tex_key], vertices, [indices[0], indices[1], indices[2]], [base_uvs[0], base_uvs[1], base_uvs[2]])
            if indices[2] != indices[3]:
                self.add_tri(faces_by_texture[tex_key], vertices, [indices[0], indices[2], indices[3]], [base_uvs[0], base_uvs[2], base_uvs[3]])
                
        return { 'name': 'Model', 'groups': faces_by_texture }

    def add_tri(self, group, vertices, indices, uvs):
        for i in range(3):
            idx = indices[i]
            x, y, z = vertices[idx*3], vertices[idx*3+1], vertices[idx*3+2]
            group['positions'].extend([x, y, z])
            group['uvs'].extend([uvs[i][0], uvs[i][1]])



def run(server_class=http.server.ThreadingHTTPServer, handler_class=ModelViewerHandler, port=8080, disc_path=None):
    if not disc_path:
        print("Error: --disc argument is required")
        sys.exit(1)

    print(f"Loading disc image: {disc_path}")
    iso_reader = ISO9660Reader(disc_path)
    
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    httpd.iso_reader = iso_reader
    
    print(f"Serving at http://localhost:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        iso_reader.close()
        httpd.server_close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='PDS Model Viewer Server')
    parser.add_argument('--disc', required=True, help='Path to game disc image (.bin)')
    parser.add_argument('--port', type=int, default=8080, help='Port to serve on')
    args = parser.parse_args()
    
    run(port=args.port, disc_path=args.disc)
