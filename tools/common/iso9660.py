import struct
import os

# ISO9660 Constants
SECTOR_SIZE = 2352
HEADER_SIZE = 16
DATA_SIZE = 2048
PVD_SECTOR = 16

def read_sector(f, sector_num):
    """Reads sector data handling Mode 1 and Mode 2 Form 1/2."""
    f.seek(sector_num * SECTOR_SIZE)
    raw = f.read(SECTOR_SIZE)
    
    if len(raw) < SECTOR_SIZE:
        return b''

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

class ISO9660Reader:
    def __init__(self, bin_path):
        self.f = open(bin_path, 'rb')
        self._parse_pvd()
        
    def _parse_pvd(self):
        # Read Primary Volume Descriptor
        self.pvd = read_sector(self.f, PVD_SECTOR)
        # Root Directory Record starts at byte 156
        self.root_record = self.pvd[156:190] 
        # Parse Root LBA (Location of Extent) - Offset 2 in record, 4 bytes LE, 4 bytes BE
        self.root_lba = struct.unpack('<I', self.root_record[2:6])[0]
        self.root_size = struct.unpack('<I', self.root_record[10:14])[0]
        
    def list_files(self):
        """Recursively list files (simple implementation)."""
        files = []
        self._scan_dir(self.root_lba, self.root_size, files)
        return files
        
    def _scan_dir(self, lba, size, file_list, path_prefix=""):
        num_sectors = (size + DATA_SIZE - 1) // DATA_SIZE
        data = b''
        for i in range(num_sectors):
            data += read_sector(self.f, lba + i)
            
        offset = 0
        while offset < len(data):
            length = data[offset]
            if length == 0: 
                # Padding or end of sector
                offset += 1
                while offset < len(data) and data[offset] == 0:
                    offset += 1
                continue
                
            record = data[offset : offset + length]
            if len(record) < 33:
                offset += length
                continue

            ext_lba = struct.unpack('<I', record[2:6])[0]
            ext_size = struct.unpack('<I', record[10:14])[0]
            flags = record[25]
            name_len = record[32]
            name = record[33 : 33 + name_len].decode('ascii', errors='ignore').split(';')[0]
            
            if name not in ['.', '..', '', '\x00', '\x01']: 
                # Note: \x00 and \x01 are current/parent dir in some ISOs
                full_name = os.path.join(path_prefix, name).replace('\\', '/') if path_prefix else name
                
                if not (flags & 2): # Not a directory
                    file_list.append({'name': full_name, 'lba': ext_lba, 'size': ext_size})
                else:
                    self._scan_dir(ext_lba, ext_size, file_list, full_name)
            
            offset += length

    def extract_file(self, lba, size):
        num_sectors = (size + DATA_SIZE - 1) // DATA_SIZE
        chunks = []
        for i in range(num_sectors):
            chunks.append(read_sector(self.f, lba + i))
        return b''.join(chunks)[:size]
        
    def close(self):
        self.f.close()
