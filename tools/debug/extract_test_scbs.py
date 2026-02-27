import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'common'))
from iso9660 import ISO9660Reader
import struct
import json

iso = ISO9660Reader(r"e:\Dev\atolm\ISOs\Panzer Dragoon Saga (USA) (Disc 1) (Track 1).bin")
files = iso.list_files()

def extract_file(name):
    matches = [f for f in files if f['name'] == name]
    if matches:
        f = matches[0]
        data = iso.extract_file(f['lba'], f['size'])
        with open(os.path.join(r"e:\Dev\atolm\output", name), "wb") as out:
            out.write(data)
        print(f"Extracted {name} ({f['size']} bytes)")

extract_file("WARNING.SCB")
extract_file("TITLEE.SCB")
extract_file("WARNING.PNB")
extract_file("TITLEE.PNB")
iso.close()
