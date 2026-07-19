#!/usr/bin/env python3
"""Ymir savestate load-address fixture (Bucket 2 deliverable 6).

Savestates are ANALYSIS FIXTURES only — never verification inputs
(charter §7). This tool answers one question: at what Saturn address is a
disc file resident in emulator memory?

Format (from Ymir's own writer, apps/ymir-sdl3/src/serdes/
cereal_savestate.hpp, verified against StrikerX3/Ymir @ HEAD 2026-07):
uncompressed cereal binary stream; the "Syst" section (4-byte magic)
serializes a few small fields, then WRAMLow (1 MiB, raw) then WRAMHigh
(1 MiB, raw), contiguously. Rather than hardcode the small-field sizes
(they can drift across savestate versions), we CALIBRATE: locate
1ST_READ.PRG's bytes (its load address 0x06006000 is disc-authoritative:
IP.BIN 1st-read-address field, offset 0xF0 — NOT 0xE8, which is the master
stack pointer that coincidentally equals it for PDS) and derive the
WRAMHigh file offset from it, then
sanity-check that offset against the "Syst" magic position (must sit
1 MiB + a small header past it — asserts the source-derived layout).

Modes:
  verify <savestate>            calibrate + report how many bytes of each
                                extracted target match at its manifest vma
  locate <savestate> <file>     report the implied load address of an
                                arbitrary extracted file (Bucket 4 overlay
                                workflow) using the calibrated base
"""
import os
import sys

from prg import REPO, load_manifests

WRAMH_SATURN_BASE = 0x06000000
ANCHOR_TARGET = "1ST_READ.PRG"
ANCHOR_VMA = 0x06006000
ANCHOR_LEN = 4096          # leading bytes used to locate the anchor


def calibrate(state):
    """Return the file offset of WRAMHigh[0], proven via the anchor."""
    anchor_path = os.path.join(REPO, "extracted", ANCHOR_TARGET)
    if not os.path.exists(anchor_path):
        sys.exit(f"ymir_fixture: extracted/{ANCHOR_TARGET} missing")
    with open(anchor_path, "rb") as f:
        needle = f.read(ANCHOR_LEN)
    idx = state.find(needle)
    if idx < 0:
        sys.exit("ymir_fixture: anchor (1ST_READ leading bytes) not found "
                 "— is this savestate from a PDS session?")
    if state.find(needle, idx + 1) >= 0:
        sys.exit("ymir_fixture: anchor bytes not unique in savestate")
    wramh = idx - (ANCHOR_VMA - WRAMH_SATURN_BASE)
    syst = state.find(b"Syst")
    if syst < 0 or not (0x100000 <= wramh - (syst + 4) <= 0x100000 + 64):
        sys.exit(f"ymir_fixture: layout sanity check failed "
                 f"(WRAMHigh@{wramh:#x}, Syst@{syst:#x}) — Ymir savestate "
                 f"format may have changed; re-read cereal_savestate.hpp")
    return wramh


def match_len(state, off, data):
    n = 0
    for i, b in enumerate(data):
        if off + i >= len(state) or state[off + i] != b:
            break
        n += 1
    return n


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    mode, state_path = sys.argv[1], sys.argv[2]
    with open(state_path, "rb") as f:
        state = f.read()
    wramh = calibrate(state)
    print(f"ymir_fixture: WRAMHigh at file offset {wramh:#x} "
          f"(calibrated via {ANCHOR_TARGET} @ {ANCHOR_VMA:#x})")

    if mode == "verify":
        for m in load_manifests():
            path = os.path.join(REPO, "extracted", m["target"])
            if not os.path.exists(path):
                continue
            with open(path, "rb") as f:
                data = f.read()
            off = wramh + (m["vma_base"] - WRAMH_SATURN_BASE)
            n = match_len(state, off, data)
            print(f"ymir_fixture: {m['target']} @ {m['vma_base']:#x}: "
                  f"{n}/{len(data)} bytes match"
                  + (" (FULL — resident and unmodified)" if n == len(data)
                     else f" (diverges at +{n:#x} = {m['vma_base']+n:#x})"))
    elif mode == "locate":
        with open(sys.argv[3], "rb") as f:
            data = f.read()
        probe = data[:ANCHOR_LEN]
        idx = state.find(probe)
        while idx >= 0:
            vma = WRAMH_SATURN_BASE + (idx - wramh)
            n = match_len(state, idx, data)
            print(f"ymir_fixture: {sys.argv[3]}: found at {vma:#x} "
                  f"({n}/{len(data)} contiguous bytes)")
            idx = state.find(probe, idx + 1)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
