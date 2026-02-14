#!/usr/bin/env python3
"""
PDS Extractor v3 — outputs data in the format expected by the working viewer.

Coordinate conventions (matching working pds_viewer_v2.html):
  Vertices:     raw_s16 / 4096.0
  Bone trans:   raw_s32 / 65536.0  
  Bone rot:     raw_s32 / 65536.0 * 360.0 (degrees)
  Bone scale:   raw_s32 / 65536.0
  Anim trans:   raw_s16 / 4096.0  (same as vertices)
  Anim rot:     raw_s16 value IS degrees
  
Working viewer data format:
  pointerTable: [{index, offset}, ...]
  models: {"3": {numVertices, vertices, quads}, ...}  (keyed by ENTRY index)
  hierarchies: [{ptrIndex, boneCount, nodes}]
  poses: [{boneCount, bones}]
  textures: {"key": {width, height, dataUrl}}  (note: dataUrl not png)
  animations: [{mode, numBones, numKeyframes, numBakedFrames, frames}]
  stats: {modelCount, hierarchyCount, etc}
"""

import struct, json, os, sys, argparse, base64, zlib, math
from pathlib import Path

# ─── ISO 9660 Reader ───
class ISO9660Reader:
    SECTOR_SIZE = 2352; SECTOR_HEADER = 16; SECTOR_DATA = 2048
    def __init__(self, path):
        self.path = path; self.f = open(path, 'rb'); self.files = {}
        self._read_pvd(); self._read_root_directory()
    def _read_sector(self, lba):
        self.f.seek(lba * self.SECTOR_SIZE + self.SECTOR_HEADER)
        return self.f.read(self.SECTOR_DATA)
    def _read_sectors(self, lba, count):
        data = bytearray()
        for i in range(count): data.extend(self._read_sector(lba + i))
        return bytes(data)
    def _read_pvd(self):
        pvd = self._read_sector(16)
        self.root_lba = struct.unpack_from('<I', pvd, 156 + 2)[0]
        self.root_size = struct.unpack_from('<I', pvd, 156 + 10)[0]
    def _read_root_directory(self): self._read_directory(self.root_lba, self.root_size, '')
    def _read_directory(self, lba, size, prefix):
        sectors_needed = (size + self.SECTOR_DATA - 1) // self.SECTOR_DATA
        data = self._read_sectors(lba, sectors_needed)
        pos = 0
        while pos < size:
            rec_len = data[pos]
            if rec_len == 0:
                nb = ((pos // self.SECTOR_DATA) + 1) * self.SECTOR_DATA
                if nb >= size: break
                pos = nb; continue
            file_lba = struct.unpack_from('<I', data, pos + 2)[0]
            file_size = struct.unpack_from('<I', data, pos + 10)[0]
            flags = data[pos + 25]; name_len = data[pos + 32]
            name = data[pos + 33:pos + 33 + name_len].decode('ascii', errors='replace')
            pos += rec_len
            if name_len == 1 and name in ('\x00', '\x01'): continue
            if ';' in name: name = name[:name.index(';')]
            full_path = f"{prefix}/{name}" if prefix else name
            if flags & 0x02: self._read_directory(file_lba, file_size, full_path)
            else: self.files[full_path] = (file_lba, file_size)
    def read_file(self, path):
        for k in self.files:
            if k.upper() == path.upper(): path = k; break
        else:
            if path not in self.files: raise FileNotFoundError(path)
        lba, size = self.files[path]
        return self._read_sectors(lba, (size + self.SECTOR_DATA - 1) // self.SECTOR_DATA)[:size]
    def list_files(self, ext=None):
        return sorted(p for p in self.files if ext is None or p.upper().endswith(ext.upper()))
    def close(self): self.f.close()

# ─── Pointer Table ───
def parse_pointer_table(data):
    offsets = []; pos = 0
    while pos + 4 <= len(data):
        val = struct.unpack_from('>I', data, pos)[0]
        if val == 0 or val >= len(data): break
        if offsets and val <= pos: break
        offsets.append(val); pos += 4
    return offsets

# ─── Classification ───
def classify_entries(data, offsets):
    entries = []
    for i, off in enumerate(offsets):
        nxt = offsets[i+1] if i+1 < len(offsets) else len(data)
        size = nxt - off
        e = {'index': i, 'offset': off, 'size': size, 'type': 'unknown'}
        if size < 12: entries.append(e); continue
        w1 = struct.unpack_from('>I', data, off + 4)[0]
        w2 = struct.unpack_from('>I', data, off + 8)[0]
        if 1 <= w1 <= 5000 and w2 < len(data) and w2 + w1*6 <= len(data):
            e['type'] = 'model'
        elif size >= 24:
            ok, nc, np = True, 0, off
            while np + 12 <= off + size and nc < 200:
                m,c,s = struct.unpack_from('>III', data, np)
                if m==0 and c==0 and s==0: break
                if (m and m>=len(data)) or (c and c>=len(data)) or (s and s>=len(data)): ok=False; break
                nc += 1; np += 12
            if ok and nc >= 2: e['type'] = 'hierarchy'; e['nodeCount'] = nc
        if e['type'] == 'unknown' and size >= 36 and size % 36 == 0:
            bc = size // 36
            if 2 <= bc <= 100:
                ok = True
                for b in range(bc):
                    for j in range(3):
                        sv = struct.unpack_from('>i', data, off + b*36 + 24 + j*4)[0]
                        if abs(sv - 0x10000) > 0x8000: ok = False; break
                    if not ok: break
                if ok: e['type'] = 'pose'; e['boneCount'] = bc
        entries.append(e)
    return entries

# ─── Model Extraction ───
def extract_model(data, offset):
    if offset + 12 > len(data): return None
    vc = struct.unpack_from('>I', data, offset + 4)[0]
    vo = struct.unpack_from('>I', data, offset + 8)[0]
    if vc == 0 or vc > 5000 or vo + vc*6 > len(data): return None
    verts = []
    for i in range(vc):
        vp = vo + i*6
        x,y,z = struct.unpack_from('>hhh', data, vp)
        verts.append([x/4096.0, y/4096.0, z/4096.0])
    quads = []; pos = offset + 12
    while pos + 20 <= len(data):
        idx = struct.unpack_from('>HHHH', data, pos)
        if idx[0]==0 and idx[1]==0 and idx[2]==0 and idx[3]==0: break
        if max(idx) >= vc + 100: break
        lc = struct.unpack_from('>H', data, pos+8)[0]
        cc = struct.unpack_from('>H', data, pos+10)[0]
        cp = struct.unpack_from('>H', data, pos+12)[0]
        cl = struct.unpack_from('>H', data, pos+14)[0]
        cs = struct.unpack_from('>H', data, pos+16)[0]
        cz = struct.unpack_from('>H', data, pos+18)[0]
        tw = ((cz>>8)&0x3F)*8; th = cz&0xFF
        cm = (cp>>3)&7; fh = bool(cc&0x10); fv = bool(cc&0x20)
        lm = (lc>>8)&3
        q = {'indices': list(idx), 'lightingMode': lm,
             'cmdctrl': cc, 'cmdpmod': cp, 'cmdcolr': cl, 'cmdsrca': cs, 'cmdsize': cz,
             'texWidth': tw, 'texHeight': th, 'colorMode': cm, 'flipH': fh, 'flipV': fv,
             'textureKey': f'{cs}_{cl}_{cz}_{cp}'}
        pos += 20
        if lm==1: pos+=8
        elif lm==2: pos+=48
        elif lm==3: pos+=24
        quads.append(q)
    return {'numVertices': vc, 'vertices': verts, 'quads': quads}

# ─── Hierarchy ───
def extract_hierarchy(data, offset, size, entries, entry_idx):
    nodes = []; visited = set()
    def walk(off, depth=0):
        if off==0 or off in visited or off+12>len(data): return
        visited.add(off)
        m,c,s = struct.unpack_from('>III', data, off)
        mi = -1
        if m:
            for e in entries:
                if e['offset']==m and e['type']=='model': mi=e['index']; break
        nodes.append({'offset':off,'modelOffset':m,'childOffset':c,'siblingOffset':s,'depth':depth,'modelIndex':mi})
        if c: walk(c, depth+1)
        if s: walk(s, depth)
    walk(offset)
    return nodes

def count_bones(data, offset):
    c = 0; vis = set()
    def w(o):
        nonlocal c
        if o==0 or o in vis or o+12>len(data): return
        vis.add(o); c+=1
        ch = struct.unpack_from('>I', data, o+4)[0]
        si = struct.unpack_from('>I', data, o+8)[0]
        if ch: w(ch)
        if si: w(si)
    w(offset); return c

# ─── Pose ───
def extract_pose(data, offset, bc):
    bones = []
    for i in range(bc):
        bp = offset + i*36
        v = struct.unpack_from('>9i', data, bp)
        bones.append({
            'translation': [v[0]/65536.0, v[1]/65536.0, v[2]/65536.0],
            'rotation': [v[3]/65536.0*360.0, v[4]/65536.0*360.0, v[5]/65536.0*360.0],
            'scale': [v[6]/65536.0, v[7]/65536.0, v[8]/65536.0]
        })
    return bones

# ─── Animation Baking ───
def bake_animation(data, offset, size, bone_count, pose):
    if size < 4: return None
    flags = data[offset]; nb = data[offset+1]
    nf = struct.unpack_from('>H', data, offset+2)[0]
    if nb==0 or nf==0: return None
    modes = []
    for i in range(nb):
        bi = 4 + (i*2)//8; bt = (i*2)%8
        modes.append((data[offset+bi]>>(6-bt))&3)
    pos = offset + 4 + math.ceil(nb*2/8)
    tracks = []
    for b in range(nb):
        if modes[b]==0: tracks.append(None); continue
        interval = {1:1,2:2,3:4}.get(modes[b],2)
        nkf = (nf + interval - 1)//interval + 1
        kfs = []
        for k in range(nkf):
            if pos+12 > offset+size: break
            kfs.append(struct.unpack_from('>6h', data, pos))
            pos += 12
        tracks.append({'interval':interval,'kfs':kfs})
    # Bake per-frame
    frames = []
    for f in range(nf):
        fb = []
        for b in range(nb):
            tr = tracks[b] if b < len(tracks) else None
            if not tr or not tr['kfs']:
                if pose and b < len(pose):
                    fb.append({
                        'translation': list(pose[b]['translation']),
                        'rotation': list(pose[b]['rotation']),
                        'scale': list(pose[b]['scale'])
                    })
                else:
                    fb.append({'translation':[0,0,0],'rotation':[0,0,0],'scale':[1,1,1]})
                continue
            ki = f / tr['interval']
            k0i = min(int(ki), len(tr['kfs'])-1)
            k1i = min(k0i+1, len(tr['kfs'])-1)
            t = ki - int(ki)
            k0,k1 = tr['kfs'][k0i], tr['kfs'][k1i]
            lerp = lambda a,b,t: a+(b-a)*t
            fb.append({
                'translation': [lerp(k0[0],k1[0],t)/4096.0, lerp(k0[1],k1[1],t)/4096.0, lerp(k0[2],k1[2],t)/4096.0],
                'rotation': [lerp(k0[3],k1[3],t), lerp(k0[4],k1[4],t), lerp(k0[5],k1[5],t)],
                'scale': [1.0, 1.0, 1.0]
            })
        frames.append(fb)
    return {'mode':4,'numBones':nb,'numKeyframes':nf,'numBakedFrames':nf,
            'hasPosition':True,'hasRotation':True,'hasScale':False,'frames':frames}

# ─── Textures ───
def decode_rgb555(p):
    r=((p)&0x1F)<<3; g=((p>>5)&0x1F)<<3; b=((p>>10)&0x1F)<<3
    a = 255 if (p&0x8000) or p!=0 else 0
    return r,g,b,a

def make_png(pixels, w, h):
    def chunk(ct, d):
        c = ct+d; return struct.pack('>I',len(d))+c+struct.pack('>I',zlib.crc32(c)&0xFFFFFFFF)
    ihdr = struct.pack('>IIBBBBB',w,h,8,6,0,0,0)
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw.extend(pixels[y*w*4:(y+1)*w*4])
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',ihdr)+chunk(b'IDAT',zlib.compress(bytes(raw),9))+chunk(b'IEND',b'')

def extract_texture(cgb, cmdsrca, cmdcolr, cmdsize, cmdpmod):
    tw=((cmdsize>>8)&0x3F)*8; th=cmdsize&0xFF; cm=(cmdpmod>>3)&7
    if tw==0 or th==0 or not cgb: return None
    bo = cmdsrca*8; px = bytearray(tw*th*4)
    if cm==5:
        for y in range(th):
            for x in range(tw):
                po=bo+(y*tw+x)*2
                if po+2>len(cgb): continue
                p=struct.unpack_from('>H',cgb,po)[0]
                r,g,b,a=decode_rgb555(p); i=(y*tw+x)*4; px[i:i+4]=bytes([r,g,b,a])
    elif cm==1:
        lo=cmdcolr*8; pal=[]
        for i in range(16):
            if lo+i*2+2<=len(cgb): pal.append(decode_rgb555(struct.unpack_from('>H',cgb,lo+i*2)[0]))
            else: pal.append((0,0,0,0))
        for y in range(th):
            for x in range(tw):
                pi=y*tw+x; b2=bo+pi//2
                if b2>=len(cgb): continue
                ci=(cgb[b2]>>4)&0xF if pi%2==0 else cgb[b2]&0xF
                r,g,b,a=pal[ci]; i=(y*tw+x)*4; px[i:i+4]=bytes([r,g,b,a])
    elif cm==0:
        for y in range(th):
            for x in range(tw):
                pi=y*tw+x; b2=bo+pi//2
                if b2>=len(cgb): continue
                ci=(cgb[b2]>>4)&0xF if pi%2==0 else cgb[b2]&0xF
                g=ci*17; i=(y*tw+x)*4; px[i:i+4]=bytes([g,g,g,255])
    elif cm==4:
        for y in range(th):
            for x in range(tw):
                b2=bo+y*tw+x
                if b2>=len(cgb): continue
                g=cgb[b2]; i=(y*tw+x)*4; px[i:i+4]=bytes([g,g,g,255])
    else:
        return None
    png = make_png(px, tw, th)
    return 'data:image/png;base64,' + base64.b64encode(png).decode('ascii')

# ─── Main Pipeline ───
def extract_mcb_cgb(mcb, cgb, name):
    offsets = parse_pointer_table(mcb)
    if not offsets: return None
    entries = classify_entries(mcb, offsets)
    
    # Pointer table (for working viewer's model lookup)
    ptr_table = [{'index':i,'offset':offsets[i]} for i in range(len(offsets))]
    
    # Models keyed by entry index (string keys for JS compat)
    models = {}
    model_entries = [e for e in entries if e['type']=='model']
    for e in model_entries:
        m = extract_model(mcb, e['offset'])
        if m: models[str(e['index'])] = m
    
    # Hierarchies
    hierarchies = []
    for e in entries:
        if e['type']!='hierarchy': continue
        bc = count_bones(mcb, e['offset'])
        nodes = extract_hierarchy(mcb, e['offset'], e['size'], entries, e['index'])
        hierarchies.append({'ptrIndex':e['index'],'boneCount':bc,'nodes':nodes})
    
    # Poses
    poses = []
    pose_entries = [e for e in entries if e['type']=='pose']
    for e in pose_entries:
        bones = extract_pose(mcb, e['offset'], e['boneCount'])
        poses.append({'boneCount':e['boneCount'],'bones':bones})
    
    # Animations (baked)
    animations = []
    if pose_entries:
        last_pi = max(e['index'] for e in pose_entries)
        pose0 = poses[0]['bones'] if poses else None
        bc = hierarchies[0]['boneCount'] if hierarchies else 0
        for e in entries:
            if e['index'] <= last_pi or e['type'] != 'unknown' or e['size'] < 4: continue
            anim = bake_animation(mcb, e['offset'], e['size'], bc, pose0)
            if anim and anim['numBakedFrames'] > 0 and anim['numBakedFrames'] <= 500: animations.append(anim)
    
    # Textures (keyed by texture key, with dataUrl)
    textures = {}
    if cgb:
        for mk, model in models.items():
            for q in model['quads']:
                tk = q['textureKey']
                if tk not in textures:
                    url = extract_texture(cgb, q['cmdsrca'], q['cmdcolr'], q['cmdsize'], q['cmdpmod'])
                    if url:
                        tw=((q['cmdsize']>>8)&0x3F)*8; th=q['cmdsize']&0xFF
                        textures[tk] = {'width':tw,'height':th,'colorMode':q['colorMode'],'dataUrl':url}
    
    tc = len(textures); mc = len(models)
    tq = sum(len(m['quads']) for m in models.values())
    tv = sum(m['numVertices'] for m in models.values())
    
    return {
        'name': name,
        'pointerTable': ptr_table,
        'models': models,
        'hierarchies': hierarchies,
        'poses': poses,
        'animations': animations,
        'textures': textures,
        'stats': {
            'modelCount':mc, 'hierarchyCount':len(hierarchies),
            'poseCount':len(poses), 'animationCount':len(animations),
            'textureCount':tc, 'totalQuads':tq, 'totalVertices':tv
        }
    }

def main():
    parser = argparse.ArgumentParser(description='PDS Extractor v3')
    parser.add_argument('disc', nargs='?')
    parser.add_argument('--mcb'); parser.add_argument('--cgb')
    parser.add_argument('-o','--output',default='extracted')
    parser.add_argument('-n','--names',nargs='*')
    parser.add_argument('--all',action='store_true')
    parser.add_argument('--list',action='store_true')
    args = parser.parse_args()
    os.makedirs(args.output, exist_ok=True)
    
    if args.mcb:
        mcb = open(args.mcb,'rb').read()
        cgb = open(args.cgb,'rb').read() if args.cgb else None
        nm = Path(args.mcb).stem
        result = extract_mcb_cgb(mcb, cgb, nm)
        if result:
            with open(os.path.join(args.output, f'{nm}.json'),'w') as f: json.dump(result, f)
        return
    
    if not args.disc: parser.error("Disc image or --mcb required")
    iso = ISO9660Reader(args.disc)
    mcbs = iso.list_files('.MCB')
    cgbs = {Path(f).stem.upper():f for f in iso.list_files('.CGB')}
    
    if args.list:
        print(f'{len(mcbs)} MCB files:')
        for f in mcbs: print(f'  {f} [CGB:{"Y" if Path(f).stem.upper() in cgbs else "N"}]')
        iso.close(); return
    
    targets = [n.upper() for n in args.names] if args.names else \
              [Path(f).stem.upper() for f in mcbs] if args.all else \
              ['DRAGON0','DRAGON1','DRAGON2','DRAGON3','DRAGON4','DRAGON5','DRAGON6','DRAGON7','EDGE','AZEL']
    
    manifest = []
    for mp in mcbs:
        stem = Path(mp).stem.upper()
        if stem not in targets: continue
        print(f'Extracting {stem}...')
        mcb = iso.read_file(mp)
        cgb = iso.read_file(cgbs[stem]) if stem in cgbs else None
        result = extract_mcb_cgb(mcb, cgb, stem)
        if result:
            with open(os.path.join(args.output, f'{stem}.json'),'w') as f: json.dump(result, f)
            s = result['stats']
            print(f'  {s["modelCount"]}m {s["totalQuads"]}q {s["textureCount"]}t {s["animationCount"]}a')
            manifest.append({'name':stem,'stats':s})
    
    with open(os.path.join(args.output,'manifest.json'),'w') as f:
        json.dump({'totalFiles':len(manifest),'files':manifest},f,indent=2)
    print(f'\nDone. {len(manifest)} files → {args.output}/')
    iso.close()

if __name__ == '__main__': main()
