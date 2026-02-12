import struct
import os
import argparse
import sys
import numpy as np
from PIL import Image
import io
try:
    from tools.yamaha_adpcm import YamahaAdpcmDecoder
except ImportError:
    from yamaha_adpcm import YamahaAdpcmDecoder


# ISO9660 Constants
SECTOR_SIZE = 2352
HEADER_SIZE = 16
DATA_SIZE = 2048
PVD_SECTOR = 16

def read_sector(f, sector_num):
    """Reads sector data handling Mode 1 and Mode 2 Form 1/2."""
    f.seek(sector_num * SECTOR_SIZE)
    raw = f.read(SECTOR_SIZE)
    
    # Mode is at offset 15
    mode = raw[15]
    
    if mode == 1:
        # Mode 1: Header 16, Data 2048
        return raw[16:16+2048]
    elif mode == 2:
        # Mode 2
        # Submode is at offset 18 (16 + 2)
        submode = raw[18]
        if submode & 0x20: # Form 2 bit
            # Form 2: Header 16, Subheader 8, Data 2324
            return raw[24:24+2324]
        else:
            # Form 1: Header 16, Subheader 8, Data 2048
            return raw[24:24+2048]
    return raw[16:16+2048] # Fallback


class IsoReader:
    def __init__(self, disc_path):
        self.disc_path = disc_path
        self.f = open(disc_path, 'rb')
        self.root_record = None
        self._parse_pvd()

    def _parse_pvd(self):
        """Parse Primary Volume Descriptor to find root directory."""
        pvd_data = read_sector(self.f, PVD_SECTOR)
        
        # Verify ISO9660 identifier
        if pvd_data[1:6] != b'CD001':
            raise ValueError("Not a valid ISO9660 disc image (missing CD001 identifier)")
            
        # Root Directory Record is at offset 156
        # The record itself starts with length (1 byte), then extended attribute length (1 byte)
        # Then sector location (8 bytes - both endian), then data length (8 bytes - both endian)
        # We just need to parse this 34-byte structure as a directory record
        self.root_record_bytes = pvd_data[156:156+34] 
        # Actually, we should just parse the root directory listing from this.
        # But for now, let's just store the sector location of the root directory.
        
        # Offset 2 in the record is the LBA (Little Endian mainly used, but both are present)
        # 156 + 2 = 158. 
        # Format of Root Directory Record in PVD:
        # 156: Length of Directory Record (1)
        # 157: Extended Attribute Record Length (1)
        # 158: Location of Extent (8 bytes, LSB-MSB) -> we want the first 4 bytes for LE
        
        self.root_sector = struct.unpack('<I', pvd_data[158:162])[0]
        self.root_size = struct.unpack('<I', pvd_data[166:170])[0]
        # print(f"Root dir at sector {self.root_sector}, size {self.root_size}")

    def list_files(self, directory_sector=None, directory_size=None, path="/"):
        """Recursively list files in the ISO."""
        if directory_sector is None:
            directory_sector = self.root_sector
            directory_size = self.root_size
            
        files = []
        
        # Read all sectors for this directory
        num_sectors = (directory_size + DATA_SIZE - 1) // DATA_SIZE
        dir_data = bytearray()
        for i in range(num_sectors):
            dir_data.extend(read_sector(self.f, directory_sector + i))
            
        offset = 0
        while offset < len(dir_data):
            # Directory Record format
            length = dir_data[offset]
            if length == 0:
                # Padding at end of sector?
                # Check if we are at a sector boundary, if so skip to next sector
                # But we concatenated data. Usually padding is zeroes until end of sector.
                # Let's try to align to next 2048 block if we hit 0?
                # Actually, ISO9660 directories records do not cross sector boundaries.
                # So if we see 0, we should skip to the next 2048-byte chunk.
                current_sector_offset = offset % DATA_SIZE
                if current_sector_offset != 0:
                    padding = DATA_SIZE - current_sector_offset
                    offset += padding
                    continue
                else:
                     # If we are exactly at boundary and see 0, or just multiple 0s, maybe done?
                     if offset >= directory_size:
                         break
                     # If we just corrected to boundary and still 0?
                     if offset < len(dir_data) and dir_data[offset] == 0:
                         # Likely end of directory usage within allocated sectors
                         break
                     continue

            if offset + length > len(dir_data):
                break
                
            record = dir_data[offset : offset + length]
            
            file_lba = struct.unpack('<I', record[2:6])[0]
            file_size = struct.unpack('<I', record[10:14])[0]
            flags = record[25]
            name_len = record[32]
            name = record[33 : 33 + name_len].decode('ascii', errors='ignore')
            
            # Helper for directory entries that are not . or ..
            if name == '\x00': name = '.'
            if name == '\x01': name = '..'
            
            # print(f"Found {name} at {file_lba}, size {file_size}, flags {flags:b}")

            full_path = os.path.join(path, name).replace("\\", "/")

            if not (flags & 2): # Not a directory
                if ';' in name:
                    name = name.split(';')[0]
                files.append({'path': full_path, 'name': name, 'lba': file_lba, 'size': file_size})
            elif name not in ['.', '..']:
                # Recurse
                 files.extend(self.list_files(file_lba, file_size, full_path))
            
            offset += length
            
        return files

    def close(self):
        self.f.close()


class SegaFilmParser:
    def __init__(self, file_data):
        self.data = file_data
        self.offset = 0
        self.header = {}
        self.frames = []
        self.audio_samples = []
        self._parse()

    def _read_u32(self):
        val = struct.unpack('>I', self.data[self.offset:self.offset+4])[0]
        self.offset += 4
        return val

    def _read_u16(self):
        val = struct.unpack('>H', self.data[self.offset:self.offset+2])[0]
        self.offset += 2
        return val
        
    def _read_bytes(self, n):
        val = self.data[self.offset:self.offset+n]
        self.offset += n
        return val

    def _parse(self):
        # Header (16 bytes? Or variable?)
        # Magic: FILM
        if self.data[0:4] != b'FILM':
             raise ValueError("Not a Sega FILM file")
        
        self.offset = 4
        # header_len = self._read_u32() # Removed extra read
        file_size = self._read_u32() 
        version = self._read_bytes(4)
        reserved = self._read_u32()
        
        # Parse Chunks
        while self.offset < len(self.data):
            if self.offset + 8 > len(self.data):
                break
            
            # Adaptive parsing: peek 4 bytes
            val1 = struct.unpack('>I', self.data[self.offset:self.offset+4])[0]
            
            # Heuristic: if val1 represents a reasonable size (e.g. < 100MB) and not ASCII
            # Assume Size, Tag.
            # STAB (0x53544142) is > 100MB.
            # cvid (0x63766964) is > 100MB.
            
            chunk_size = 0
            chunk_tag = b''
            
            if val1 < 0x10000000: # Less than 256MB -> Size
                 chunk_size = self._read_u32()
                 chunk_tag = self._read_bytes(4)
            else: # Assume Tag
                 chunk_tag = self._read_bytes(4)
                 chunk_size = self._read_u32()
            
            print(f"Found chunk: {chunk_tag} size: {chunk_size} at offset {self.offset-8}")

            if chunk_size <= 8:
                 print(f"Invalid chunk size {chunk_size}, stopping parse.")
                 break

            chunk_end = self.offset + chunk_size - 8 
            
            data_start = self.offset
            data_len = chunk_size - 8
            
            # Debug dump
            print(f"Chunk Data: {self.data[data_start:data_start+min(32, data_len)].hex()}")

            if chunk_tag == b'FDSC' or chunk_tag == b'cvid':
                self._parse_fdsc(data_start, data_len)
            elif chunk_tag == b'STAB' or chunk_tag == b'\x00\x00\x02X': # 0x58 = X
                # Actually tag was bytes 00 00 02 58
                self._parse_stab(data_start, data_len)
                # The data starts immediately after the STAB chunk?
                # Or at 23760?
                # chunk_end is calculated as offset + chunk_size - 8
                # self.offset becomes chunk_end at end of loop.
                # So we can capture chunk_end here?
                self.base_offset = chunk_end
            elif chunk_tag == b'CVID':
                pass 
            
            self.offset = data_start + data_len

    def _parse_fdsc(self, start, length):
        # Frame Description
        # 0: codec (4 bytes) "cvid"
        # 4: height (u32) ? No.
        # Format (from wiki/ffmpeg):
        # 0: codec fourcc
        # 4: height (32 encoded?) 
        # 8: width
        # 12: bit depth
        # ...
        # Actually structure is often:
        # FourCC (4)
        # Height (4)
        # Width (4)
        # BPP (1)
        # Channels(1) ?
        
        # Let's peek at the data layout when we run it.
        # Assuming standard header for now based on ffmpeg segafilm.c source:
        # AVCodecTag codec_tag; (4)
        # width (4)
        # height (4)
        # time_base (4) ?
        
        curr = self.offset
        codec = self.data[curr:curr+4]
        self.header['codec'] = codec.decode('ascii')
        
        self.header['height'] = struct.unpack('>I', self.data[curr+4:curr+8])[0]
        self.header['width'] = struct.unpack('>I', self.data[curr+8:curr+12])[0]
        self.header['unknown'] = struct.unpack('>I', self.data[curr+12:curr+16])[0]
        
        # Audio Format (FDSC offset 12 in payload? or offset 28 in chunk?)
        # From logs: 18 01 10 00 at offset 12 in payload.
        # Payload starts at curr.
        # 0-3: Codec
        # 4-7: Height
        # 8-11: Width
        # 12: Unknown? Wait.
        # Log: 63766964 (0-3) | 000000b0 (4-7) | 00000140 (8-11) | 18011000 (12-15)
        # My unpack above:
        # height = 000000b0 (176) -> Correct
        # width = 00000140 (320) -> Correct
        # unknown = 18011000? No.
        # Log said: 63766964 000000b0 00000140 18011000
        # self.data[curr+12:curr+16] IS 18011000.
        
        # So 'unknown' IS the Audio Format field?
        # Let's parse it properly.
        af_bytes = self.data[curr+12:curr+16]
        self.header['audio_encoding'] = af_bytes[0] # 18
        self.header['channels'] = af_bytes[1]      # 01
        self.header['bit_depth'] = af_bytes[2]     # 10
        self.header['unknown_af'] = af_bytes[3]    # 00
        
        # Dump full FDSC for analysis
        print(f"DEBUG: FDSC Raw: {self.data[curr:curr+32].hex()}")
        
        # It seems width and height are there.
        # print(f"FDSC: {self.header}")

    def _parse_stab(self, start, length):
        # Sample Table
        # Header appears to be 16 bytes
        curr = start
        val1 = struct.unpack('>I', self.data[curr:curr+4])[0]
        num_frames = struct.unpack('>I', self.data[curr+4:curr+8])[0]
        val3 = struct.unpack('>I', self.data[curr+8:curr+12])[0]
        val4 = struct.unpack('>I', self.data[curr+12:curr+16])[0]
        
        self.header['fps_val'] = val1
        self.header['frame_count'] = num_frames
        
        print(f"STAB Header: Val1={val1}, Frames={num_frames}, Val3={val3}, Val4={val4}")
        
        curr += 16
        
        # Entries
        # Heuristic from first entry dump: FFFFFFFF 00000001 00007D00 00003EE0
        # Maybe Offset, Size, Flags, ...?
        # But 00003EE0 (16096) is suspicious if it's offset.
        # Maybe relative to end of STAB?
        # End of STAB is ~23760.
        # 23760 + 16096 = 39856.
        # Let's collect them and see.
        
        for i in range(num_frames):
            if curr + 16 > start + length:
                break
                
            e1 = struct.unpack('>I', self.data[curr:curr+4])[0] # Offset?
            e2 = struct.unpack('>I', self.data[curr+4:curr+8])[0] # Size? Flags?
            e3 = struct.unpack('>I', self.data[curr+8:curr+12])[0] 
            e4 = struct.unpack('>I', self.data[curr+12:curr+16])[0]
            
            if len(self.frames) < 20:
                print(f"DEBUG STAB: Frame {len(self.frames)}: e1={e1:08x}, e2={e2:08x}, e3={e3:08x}, e4={e4:08x}")

            self.frames.append({'e1': e1, 'e2': e2, 'e3': e3, 'e4': e4})
            curr += 16
            
        print(f"Parsed {len(self.frames)} frames.")
    def extract_audio(self):
        # Extract audio chunks, processing each
        # Returns list of bytearrays (LE 16-bit PCM)
        audio_chunks = []
        base = getattr(self, 'base_offset', 0)
        
        # Check Format
        is_adpcm = (self.header.get('audio_encoding') == 0x18)
        decoder = None
        if is_adpcm:
            print("Detected ADPCM Audio (Type 0x18). Using YamahaAdpcmDecoder (SCSP).")
            decoder = YamahaAdpcmDecoder()
        else:
            print(f"Assuming PCM Audio (Encoding {self.header.get('audio_encoding', 'Unknown')})")

        for f in self.frames:
            # Audio Chunk Indentification
            # Standard FILM: Info field (e1) is 0xFFFFFFFF
            is_audio = (f['e1'] == 0xFFFFFFFF)
            
            if is_audio and f['e4'] > 0:
                off = f['e3'] + base
                sz = f['e4']
                
                if off + sz <= len(self.data):
                    chunk = self.data[off:off+sz]
                    
                    # 1. Header Stripping
                    # Analysis showed 16-byte header in audio chunks.
                    # 0-3: Size
                    # 4-7: W/H
                    # 8-11: 0001 0000 (Channels?)
                    # 12: Step Index?
                    # 13: ?
                    # 14-15: Size-4?
                    
                    if len(chunk) > 16:
                        step_index = chunk[12]
                        # Predictor? offset 10-11 is 0000.
                        # predictor = struct.unpack('>h', chunk[10:12])[0]
                        
                        chunk = chunk[16:]
                    
                    if is_adpcm:
                        # Decode ADPCM -> List of Samples
                        # Pass initial state if decoder supports it
                        # AICA/Saturn uses Low-High nibble order.
                        # Do not pass initial state (None) to preserve stream continuity.
                        samples = decoder.decode(chunk, nibble_order='lo_hi')
                        # Pack to LE 16-bit PCM
                        chunk_pcm = struct.pack(f'<{len(samples)}h', *samples)
                        audio_chunks.append(chunk_pcm)

                    else:
                        # Normalize PCM (BE -> LE)
                        # Assume Signed 16-bit BE
                        if len(chunk) % 2 != 0: chunk = chunk[:-1]
                        a_swap = bytearray(len(chunk))
                        a_swap[0::2] = chunk[1::2] # LE Low = BE High? No.
                        # BE: [H L]
                        # LE: [L H]
                        # a_swap[0] (L) = chunk[1] (L)
                        # a_swap[1] (H) = chunk[0] (H)
                        a_swap[0::2] = chunk[1::2]
                        a_swap[1::2] = chunk[0::2]
                        audio_chunks.append(a_swap)

                else:
                     print(f"Warning: Audio frame at {off} truncated")
        
        return audio_chunks

    def extract_video_frames(self):
         # Generator yielding video frames
        base = getattr(self, 'base_offset', 0)
        for i, f in enumerate(self.frames):
            # Pass all chunks with data to decoder, let decoder validate
            if f['e4'] > 0: 
                off = f['e3'] + base
                sz = f['e4']
                if off + sz <= len(self.data):
                     yield self.data[off:off+sz]


                        # Save Video Frames


class CinepakDecoder:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.yuv_image = np.zeros((height, width, 3), dtype=np.float32)
        # Flattened codebooks for faster access? 
        # V4: 256 vectors, each is a 2x2 patch (4 pixels) used to tile a 4x4 block
        # V1: 256 vectors, each is a 2x2 patch (4 pixels) used to fill a 4x4 block (upscaled)
        self.v4_codebook = np.zeros((256, 4, 3), dtype=np.float32)
        self.v1_codebook = np.zeros((256, 4, 3), dtype=np.float32)
        
    def decode_frame(self, data):
        """Decodes a frame, returns PIL Image."""
        if len(data) < 16: return None
        
        # print(f"DEBUG: Frame Header: {data[:16].hex()}")

        flags = data[0]
        size = (data[1] << 16) | (data[2] << 8) | data[3]
        w = (data[4] << 8) | data[5]
        h = (data[6] << 8) | data[7]
        num_strips = (data[8] << 8) | data[9]
        
        # print(f"DEBUG: Frame flags={flags:02x} size={size} w={w} h={h} strips={num_strips}")
        
        if w != self.width or h != self.height:
            return None
            
        offset = 12 # Header appears to be 12 bytes (padded 10-11)
        
        for i in range(num_strips):
            if offset >= len(data): break
            # Strip Header
            strip_id = (data[offset] << 8) | data[offset+1]
            strip_size = (data[offset+2] << 8) | data[offset+3]
            
            # print(f"DEBUG: Strip {i} ID={strip_id:04x} Size={strip_size} Offset={offset}")

            # sanity check
            if strip_id not in [0x1000, 0x1100]:
                offset += 2 # Try to skip?
                continue
                
            sy = (data[offset+4] << 8) | data[offset+5]
            sx = (data[offset+6] << 8) | data[offset+7]
            sh = (data[offset+8] << 8) | data[offset+9]
            sw = (data[offset+10] << 8) | data[offset+11]
            
            # print(f"DEBUG: Strip {i} ID={strip_id:04x} Size={strip_size} Offset={offset} SX={sx} SY={sy} SW={sw} SH={sh}")
            
            strip_data = data[offset+12 : offset+strip_size]
            self._decode_strip(strip_data, sx, sy, sw, sh)
            
            offset += strip_size
            
        # Convert YUV to RGB
        Y = self.yuv_image[:,:,0]
        U = self.yuv_image[:,:,1]
        V = self.yuv_image[:,:,2]
        
        R = Y + 1.402 * V
        G = Y - 0.34414 * U - 0.71414 * V
        B = Y + 1.772 * U
        
        rgb = np.stack([R, G, B], axis=-1)
        np.clip(rgb, 0, 255, out=rgb)
        return Image.fromarray(rgb.astype(np.uint8))

    def _decode_strip(self, data, sx, sy, sw, sh):
        offset = 0
        while offset < len(data):
            if offset + 4 > len(data): break
            chunk_id = (data[offset] << 8) | data[offset+1]
            chunk_size = (data[offset+2] << 8) | data[offset+3]
            
            # print(f"DEBUG: Chunk ID={chunk_id:04x} Size={chunk_size}")

            chunk_payload = data[offset+4 : offset+chunk_size]
            
            if chunk_id == 0x2000 or chunk_id == 0x2200:
                self._update_codebook_v4(chunk_payload, chunk_id == 0x2200)
            elif chunk_id == 0x2100 or chunk_id == 0x2300:
                self._update_codebook_v1(chunk_payload, chunk_id == 0x2300)
            elif chunk_id == 0x3000:
                 self._decode_vectors(chunk_payload, sx, sy, sw, sh, intrastrip=True)
            elif chunk_id == 0x3100:
                 self._decode_vectors(chunk_payload, sx, sy, sw, sh, intrastrip=False)
            elif chunk_id == 0x3200:
                 self._decode_vectors(chunk_payload, sx, sy, sw, sh, intrastrip=False) # Keyframe Inter? 
            
            offset += chunk_size

    def _update_codebook_v4(self, data, partial):
        self._update_codebook(data, partial, self.v4_codebook)
        
    def _update_codebook_v1(self, data, partial):
        self._update_codebook(data, partial, self.v1_codebook)

    def _update_codebook(self, data, partial, codebook):
        # print(f"DEBUG: Updating codebook partial={partial} len={len(data)}")
        if len(data) == 0:
            return
            
        offset = 0
        if partial:
            # layout: [mask 32bit] [entries...]
            # Iterate 0..255. Check mask bit. If set, read entry.
            mask_bytes = data[0:32] # Wait, mask is 32 bits = 4 bytes?
            # Usually mask is interleaved? 
            # Reference: "If the chunk has the Partial bit set, the first 32 bytes contain a bitmask"
            # 32 bytes = 256 bits. One bit per entry.
            mask_bytes = data[0:32]
            offset = 32
            
            # Use numpy to optimize bit check? or simple loop.
            # 256 entries.
            for i in range(256):
                byte_idx = i // 8
                bit_idx = 7 - (i % 8)
                if (mask_bytes[byte_idx] >> bit_idx) & 1:
                    # Read 6 bytes
                    entry = data[offset:offset+6]
                    offset += 6
                    self._parse_entry(codebook, i, entry)
        else:
            # Full update
            for i in range(256):
                entry = data[offset:offset+6]
                offset += 6
                self._parse_entry(codebook, i, entry)

    def _parse_entry(self, codebook, idx, entry):
        # Entry: Y0 Y1 Y2 Y3 U V
        y0, y1, y2, y3 = entry[0], entry[1], entry[2], entry[3]
        # Swapped U and V to fix color issues (Blue faces)
        v, u = struct.unpack('bb', entry[4:6]) # Signed

        # Store as YUV floats/int
        
        # Store as YUV floats/int
        # Codebook shape: (256, 16, 3) for V4?
        # Actually, let's store (256, 4, 3) for the 2x2 patch for V4 codebook.
        # But for V1 codebook, it also stores a 2x2 patch.
        # My init said: v4_codebook (256, 16, 3), v1_codebook (256, 4, 3)
        # Wait, if V4 codebook stores 2x2 patches, why (256, 16, 3)?
        # Ah, V4 applied to 4x4 block means 4 indices. Each index -> 2x2 patch.
        # So codebook stores 2x2 patches. 2x2 = 4 pixels.
        # So v4_codebook should be (256, 4, 3).
        
        # Let's fix the init shape logic in my head.
        # V4 Codebook: 256 entries. Each entry = 2x2 patch.
        # V1 Codebook: 256 entries. Each entry = 2x2 patch.
        # When V1 used: Upscale 2x2 patch to 4x4.
        # When V4 used: Use 4 entries to fill 4x4.
        
        # So both codebooks are (256, 2, 2, 3) or (256, 4, 3).
        
        # Pixel mapping:
        # P0 P1
        # P2 P3
        # flattened: P0, P1, P2, P3
        
        codebook[idx, 0] = [y0, u, v]
        codebook[idx, 1] = [y1, u, v]
        codebook[idx, 2] = [y2, u, v]
        codebook[idx, 3] = [y3, u, v]

    def _decode_vectors(self, data, sx, sy, sw, sh, intrastrip):
        offset = 0
        num_blocks_x = (sw + 3) // 4
        num_blocks_y = (sh + 3) // 4
        
        # We process blocks.
        # We need a mask "feeder"
        mask = 0
        mask_bits = 0
        
        # Helper to safely get bit
        def get_bit():
            nonlocal mask, mask_bits, offset
            if mask_bits == 0:
                if offset + 4 > len(data):
                    return 0 # OOB
                mask = (data[offset] << 24) | (data[offset+1] << 16) | (data[offset+2] << 8) | data[offset+3]
                offset += 4
                mask_bits = 32
            
            bit = (mask >> 31) & 1
            mask = (mask << 1) & 0xFFFFFFFF
            mask_bits -= 1
            return bit

        for by in range(num_blocks_y):
            for bx in range(num_blocks_x):
                # Calculate pixel coords
                x = sx + bx * 4
                y = sy + by * 4
                
                # Check bounds
                if x >= self.width or y >= self.height: continue

                coded = True
                if not intrastrip:
                    coded = get_bit() == 1
                
                if coded:
                    mode = get_bit()
                    if mode == 0: # V1 (1 byte)
                        if offset >= len(data): break
                        idx = data[offset]
                        offset += 1
                        
                        # Apply V1 patch (upscaled 2x2 -> 4x4)
                        entry = self.v1_codebook[idx] # Shape (4, 3)
                        
                        # Entry: P0(TL), P1(TR), P2(BL), P3(BR)
                        # Upscale:
                        patch = np.empty((4, 4, 3), dtype=np.float32)
                        
                        # TL
                        patch[0:2, 0:2] = entry[0]
                        # TR
                        patch[0:2, 2:4] = entry[1]
                        # BL
                        patch[2:4, 0:2] = entry[2]
                        # BR
                        patch[2:4, 2:4] = entry[3]
                        
                        # Clip to boundaries
                        h_end = min(y+4, self.height)
                        w_end = min(x+4, self.width)
                        
                        self.yuv_image[y:h_end, x:w_end] = patch[0:h_end-y, 0:w_end-x]

                    else: # V4 (4 bytes)
                        if offset + 4 > len(data): break
                        i0, i1, i2, i3 = data[offset], data[offset+1], data[offset+2], data[offset+3]
                        offset += 4
                        
                        # Apply 4 V4 entries
                        # i0: TL (2x2), i1: TR, i2: BL, i3: BR
                        
                        patch = np.zeros((4, 4, 3), dtype=np.float32)
                        
                        # TL
                        patch[0:2, 0:2] = self.v4_codebook[i0].reshape(2, 2, 3)
                        # TR
                        patch[0:2, 2:4] = self.v4_codebook[i1].reshape(2, 2, 3)
                        # BL
                        patch[2:4, 0:2] = self.v4_codebook[i2].reshape(2, 2, 3)
                        # BR
                        patch[2:4, 2:4] = self.v4_codebook[i3].reshape(2, 2, 3)
                        
                        h_end = min(y+4, self.height)
                        w_end = min(x+4, self.width)
                        self.yuv_image[y:h_end, x:w_end] = patch[0:h_end-y, 0:w_end-x]

def main():
    print("Starting cpk_extract...")
    parser = argparse.ArgumentParser(description="Extract Cinepak files from Sega Saturn disc image")
    parser.add_argument('--disc', help="Path to filesystem driver (ISO/BIN)")
    parser.add_argument('--list', action='store_true', help="List all files")
    parser.add_argument('--extract', help="Extract a specific CPK file (by path on disc) to output dir")
    parser.add_argument('--cpk', help="Extract audio/video from a local CPK file") # Added --cpk argument
    parser.add_argument('--output', help="Output directory", default="output")
    
    args = parser.parse_args()
    
    if args.output:
        if not os.path.exists(args.output):
            os.makedirs(args.output)
            
    if args.disc:
        try:
            reader = IsoReader(args.disc)
            
            if args.list:
                print(f"Index of {args.disc}:")
                files = reader.list_files()
                cpk_count = 0
                for f in files:
                    if f['name'].upper().endswith('.CPK'):
                        print(f"  [CPK] {f['path']} (Size: {f['size']} bytes)")
                        if not args.list: 
                             pass
                        cpk_count += 1
                    elif args.list:
                        print(f"  {f['path']} (Size: {f['size']} bytes)")
                print(f"\nFound {cpk_count} CPK files.")
                
            elif args.extract:
                target_path = args.extract
                files = reader.list_files()
                target_file = next((f for f in files if f['path'] == target_path or f['name'] == target_path), None)
                
                if target_file:
                    print(f"Extracting {target_file['path']}...")
                    data = bytearray()
                    lba = target_file['lba']
                    size = target_file['size']
                    
                    # Read sector-by-sector
                    num_sectors = (size + 2048 - 1) // 2048
                    # Correction: assume Mode 2 Form 2 capacity for calculation if needed? 
                    # But IsoReader uses 2048 divisor. 
                    # Does read_sector return 2324 bytes?
                    # If so, data buffer will be larger.
                    
                    for i in range(num_sectors):
                        chunk = read_sector(reader.f, lba + i)
                        data.extend(chunk)
                    
                    # Truncate to size?
                    # If sectors are Mode 2 Form 2, data is contiguous.
                    # size should match.
                    file_data = data[:size]
                    
                    # Save raw CPK for external viewing
                    raw_cpk_path = os.path.join(args.output, os.path.basename(target_path))
                    with open(raw_cpk_path, 'wb') as f:
                        f.write(file_data)
                    print(f"Saved raw CPK to {raw_cpk_path}")
                    
                    # Parse FILM
                    try:
                        film = SegaFilmParser(file_data)
                        print(f"Parsed FILM: {film.header}")
                        
                        # Save Audio
                        audio_chunks = film.extract_audio()
                        
                        if len(audio_chunks) > 0:
                            import wave
                            
                            # Concatenate normalized chunks
                            audio_data = b''.join(audio_chunks)
                            
                            channels = film.header.get('channels', 1)
                            rate = 32000 # Default PDS
                            
                            filename = f"{os.path.basename(target_path)}_audio.wav"
                            path = os.path.join(args.output, filename)
                            
                            with wave.open(path, 'wb') as w:
                                w.setnchannels(channels) # 1 or 2
                                w.setsampwidth(2) # 16-bit
                                w.setframerate(rate)
                                w.writeframes(audio_data)
                            print(f"Saved Audio: {path}")
                        
                        # Save Video Frames
                        print("Initializing Cinepak Decoder...")
                        decoder = CinepakDecoder(film.header['width'], film.header['height'])
                        
                        v_idx = 0
                        for v_data in film.extract_video_frames():
                            try:
                                img = decoder.decode_frame(v_data)
                                if img:
                                    png_path = os.path.join(args.output, f"frame_{v_idx:04d}.png")
                                    img.save(png_path)
                            except Exception as e:
                                print(f"Error decoding frame {v_idx}: {e}")
                            v_idx += 1
                            if v_idx % 100 == 0:
                                print(f"Saved {v_idx} frames...")
                        print(f"Saved {v_idx} video frames.")
                            
                    except Exception as e:
                        print(f"Failed to parse FILM: {e}")
                        import traceback
                        traceback.print_exc()
                        
                else:
                    print(f"File {target_path} not found.")
            
            else:
                files = reader.list_files()
                for f in files:
                    if f['name'].upper().endswith('.CPK'):
                         print(f"  [CPK] {f['path']} (Size: {f['size']} bytes)")
                print(f"\nFound {len([f for f in files if f['name'].upper().endswith('.CPK')])} CPK files.")

            reader.close()
        except Exception as e:
            print(f"Error reading {args.disc}: {e}")
            import traceback
            traceback.print_exc()
            
    if args.cpk:
        cpk_path = args.cpk
        if not os.path.exists(cpk_path):
            print(f"File not found: {cpk_path}")
            return

        print(f"Processing local CPK: {cpk_path}")
        with open(cpk_path, 'rb') as f:
            file_data = f.read()

        try:
            film = SegaFilmParser(file_data)
            print(f"Parsed FILM: {film.header}")
            
            # Save Audio
            audio_chunks = film.extract_audio()
            
            if len(audio_chunks) > 0:
                import wave
                
                # Concatenate normalized chunks
                audio_data = b''.join(audio_chunks)
                
                channels = film.header.get('channels', 1)
                rate = 32000 # Default PDS
                
                filename = f"{os.path.basename(cpk_path)}_audio.wav"
                path = os.path.join(args.output, filename)
                
                with wave.open(path, 'wb') as w:
                    w.setnchannels(channels) # 1 or 2
                    w.setsampwidth(2) # 16-bit
                    w.setframerate(rate)
                    w.writeframes(audio_data)
                print(f"Saved Audio: {path}")
            
            # Save Video Frames + Mux to AVI
            print("Initializing Cinepak Decoder and AVI Muxer...")
            decoder = CinepakDecoder(film.header['width'], film.header['height'])
            
            avi_path = os.path.join(args.output, f"{os.path.basename(cpk_path)}.avi")
            muxer = AviMuxer(avi_path, film.header['width'], film.header['height'], fps=15) # Assuming 15fps
            
            v_idx = 0
            for v_data in film.extract_video_frames():
                try:
                    img = decoder.decode_frame(v_data)
                    if img:
                        # Mux to AVI
                        muxer.add_frame(img)
                        
                except Exception as e:
                    print(f"Error decoding frame {v_idx}: {e}")
                v_idx += 1
                if v_idx % 100 == 0:
                    print(f"Processed {v_idx} frames...")
            
            muxer.close()
            print(f"Saved AVI Video: {avi_path}")
            print(f"Processed {v_idx} video frames.")

        except Exception as e:
            print(f"Failed to parse FILM: {e}")
            import traceback
            traceback.print_exc()

class AviMuxer:
    def __init__(self, filename, width, height, fps=15):
        self.filename = filename
        self.width = width
        self.height = height
        self.fps = fps
        self.frames = []
        self.idx = []
        self.movi_offset = 0

    def add_frame(self, img):
        import io
        output = io.BytesIO()
        img.save(output, format='JPEG')
        jpeg_data = output.getvalue()
        self.frames.append(jpeg_data)

    def close(self):
        with open(self.filename, 'wb') as f:
            # Write RIFF header placeholder
            f.write(b'RIFF\0\0\0\0AVI ')
            
            # Write hdrl LIST
            self._write_hdrl_list(f)
            
            # Write movi LIST
            # offsets in idx1 are relative to the 'movi' 4cc code (not the LIST start)
            movi_list_start = f.tell()
            f.write(b'LIST\0\0\0\0movi')
            saved_movi_pos = f.tell() - 4
            movi_base_offset = f.tell() # Pointing to after 'movi', effectively +12 from start?
            # Wait, standard says relative to the 'movi' identifier.
            # The 'movi' identifier is at movi_list_start + 8.
            movi_id_pos = movi_list_start + 8
            
            # Write frames
            for i, frame_data in enumerate(self.frames):
                # Align chunk to word boundary
                if f.tell() % 2 != 0:
                    f.write(b'\0')

                # Calculate offset relative to 'movi' 4cc
                current_pos = f.tell()
                offset = current_pos - movi_id_pos
                
                size = len(frame_data)
                
                f.write(b'00dc')
                f.write(struct.pack('<I', size))
                f.write(frame_data)
                
                # Pad payload if odd (not included in size)
                if size % 2 != 0:
                    f.write(b'\0')
                
                # Flags: 0x10 = Keyframe (all MJPEG frames are keyframes)
                self.idx.append((0x63643030, 0x10, offset, size))
                
            movi_size = f.tell() - movi_list_start - 8
            current_pos = f.tell()
            f.seek(saved_movi_pos)
            f.write(struct.pack('<I', movi_size))
            f.seek(current_pos)
            
            # Write idx1
            self._write_idx1(f)
            
            # Update RIFF size
            file_size = f.tell() - 8
            f.seek(4)
            f.write(struct.pack('<I', file_size))

    def _write_hdrl_list(self, f):
        # Calculate microseconds per frame
        us_per_frame = int(1000000 / self.fps)
        num_frames = len(self.frames)
        
        hdrl_start = f.tell()
        f.write(b'LIST\0\0\0\0hdrl')
        saved_hdrl_pos = f.tell() - 4
        
        # avih
        f.write(b'avih')
        f.write(struct.pack('<I', 56)) # Size of avih
        f.write(struct.pack('<I', us_per_frame)) # Microsec per frame
        f.write(struct.pack('<I', 0)) # Max bytes per sec (approx)
        f.write(struct.pack('<I', 0)) # Padding
        f.write(struct.pack('<I', 0x10)) # Flags (AVIF_HASINDEX)
        f.write(struct.pack('<I', num_frames)) # Total Frames
        f.write(struct.pack('<I', 0)) # Initial Frames
        f.write(struct.pack('<I', 1)) # Streams
        f.write(struct.pack('<I', 0)) # Suggested BufferSize
        f.write(struct.pack('<I', self.width)) # Width
        f.write(struct.pack('<I', self.height)) # Height
        f.write(b'\0' * 16) # Reserved
        
        # strl LIST
        strl_start = f.tell()
        f.write(b'LIST\0\0\0\0strl')
        saved_strl_pos = f.tell() - 4
        
        # strh
        f.write(b'strh')
        f.write(struct.pack('<I', 56)) # Size
        f.write(b'vids') # Type
        f.write(b'MJPG') # Handler
        f.write(b'\0\0\0\0') # Flags
        f.write(b'\0\0') # Priority
        f.write(b'\0\0') # Language
        f.write(b'\0\0\0\0') # Initial Frames
        f.write(struct.pack('<I', 1)) # Scale
        f.write(struct.pack('<I', self.fps)) # Rate
        f.write(b'\0\0\0\0') # Start
        f.write(struct.pack('<I', num_frames)) # Length
        f.write(struct.pack('<I', 0)) # Suggested Buffer Size
        f.write(struct.pack('<I', 10000)) # Quality
        f.write(struct.pack('<I', 0)) # Sample Size
        f.write(struct.pack('<H', 0)) # Frame left
        f.write(struct.pack('<H', 0)) # Frame top
        f.write(struct.pack('<H', self.width)) # Frame right
        f.write(struct.pack('<H', self.height)) # Frame bottom
        
        # strf
        f.write(b'strf')
        f.write(struct.pack('<I', 40)) # Size of BITMAPINFOHEADER
        f.write(struct.pack('<I', 40)) # Size
        f.write(struct.pack('<i', self.width))
        f.write(struct.pack('<i', self.height))
        f.write(struct.pack('<H', 1)) # Planes
        f.write(struct.pack('<H', 24)) # Bitcount
        f.write(b'MJPG') # Compression
        f.write(struct.pack('<I', self.width * self.height * 3)) # Size Image
        f.write(struct.pack('<i', 0)) # XPelsPerMeter
        f.write(struct.pack('<i', 0)) # YPelsPerMeter
        f.write(struct.pack('<I', 0)) # ClrUsed
        f.write(struct.pack('<I', 0)) # ClrImportant
        
        # Update strl size
        strl_size = f.tell() - strl_start - 8
        current_pos = f.tell()
        f.seek(saved_strl_pos)
        f.write(struct.pack('<I', strl_size))
        f.seek(current_pos)
        
        # Update hdrl size
        hdrl_size = f.tell() - hdrl_start - 8
        current_pos = f.tell()
        f.seek(saved_hdrl_pos)
        f.write(struct.pack('<I', hdrl_size))
        f.seek(current_pos)

    def _write_idx1(self, f):
        f.write(b'idx1')
        size = len(self.idx) * 16
        f.write(struct.pack('<I', size))
        for chunk_id, flags, offset, chunk_size in self.idx:
            f.write(struct.pack('<I', chunk_id)) # 00dc
            f.write(struct.pack('<I', flags))
            f.write(struct.pack('<I', offset))
            f.write(struct.pack('<I', chunk_size))

if __name__ == '__main__':
    main()
