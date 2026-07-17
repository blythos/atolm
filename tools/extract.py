#!/usr/bin/env python3
"""make extract: pull every config/targets/*.yaml target from ISOs/ into
extracted/, refusing to keep anything whose size or sha256 doesn't match the
manifest (wrong disc or bad dump is caught here, before any build).
"""
import glob
import hashlib
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iso9660 import ISO9660Reader

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Data track of each disc, located by glob so dump naming conventions vary a
# little without breaking. The disc is the user's own; only ISOs/ is searched.
DISC_GLOBS = {
    1: "ISOs/*Disc 1*Track 1*.bin",
}


def fail(msg):
    print(f"extract: FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    manifests = sorted(glob.glob(os.path.join(REPO, "config/targets/*.yaml")))
    if not manifests:
        fail("no target manifests in config/targets/")

    readers = {}
    ok = 0
    for path in manifests:
        with open(path) as f:
            m = yaml.safe_load(f)
        target, disc = m["target"], m["disc"]

        if disc not in readers:
            hits = glob.glob(os.path.join(REPO, DISC_GLOBS[disc]))
            if len(hits) != 1:
                fail(f"need exactly one match for {DISC_GLOBS[disc]!r} in ISOs/, "
                     f"found {len(hits)} — supply your own disc image")
            readers[disc] = ISO9660Reader(hits[0])

        r = readers[disc]
        files = {f["name"]: f for f in r.list_files()}
        if m["disc_path"] not in files:
            fail(f"{target}: {m['disc_path']} not found on disc {disc}")
        info = files[m["disc_path"]]
        data = r.extract_file(info["lba"], info["size"])

        if len(data) != m["size"]:
            fail(f"{target}: size {len(data)} != manifest {m['size']}")
        digest = hashlib.sha256(data).hexdigest()
        if digest != m["sha256"]:
            fail(f"{target}: sha256 {digest} != manifest {m['sha256']}")

        out = os.path.join(REPO, "extracted", target)
        with open(out, "wb") as f:
            f.write(data)
        print(f"extract: OK {target} ({len(data)} bytes, sha256 {digest[:16]}…)")
        ok += 1

    for r in readers.values():
        r.close()
    print(f"extract: {ok}/{len(manifests)} targets verified into extracted/")


if __name__ == "__main__":
    main()
