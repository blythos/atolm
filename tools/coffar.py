#!/usr/bin/env python3
"""Minimal ar + SH-COFF reader for library fingerprinting (Bucket 3).

The SDTK ships each SBL/SGL library twice: SYSROF .LIB (SHC toolchain) and
ar .A (GNU sh-coff toolchain). This module reads the .A variants and yields
the same (name, tool, sections) shape tools/sysrof.py produces, so
tools/libscan.py can scan both. Relocation entries wildcard 4 bytes at
their vaddr (IMM32 pool entries and branch fields alike — over-wildcarding
costs sensitivity, never correctness).
"""
import struct
from dataclasses import dataclass, field


@dataclass
class Section:
    name: str
    length: int
    align: int = 4
    contents: int = 0  # 0 = code, 0x10 = data (mirrors sysrof convention)
    data: bytes = b""
    covered: bytes = b""
    reloc_holes: list = field(default_factory=list)


@dataclass
class Module:
    name: str = ""
    tool: str = "GNU_COFF"
    sections: list = field(default_factory=list)
    offset: int = 0


def ar_members(path):
    data = open(path, "rb").read()
    assert data[:8] == b"!<arch>\n", f"{path}: not an ar archive"
    off = 8
    while off + 60 <= len(data):
        hdr = data[off:off + 60]
        name = hdr[0:16].decode("ascii", "replace").strip().rstrip("/")
        try:
            size = int(hdr[48:58].split()[0])
        except (ValueError, IndexError):
            break
        body = data[off + 60:off + 60 + size]
        if name and not name.startswith(("/", "ARFILEN")):  # skip symtab/strtab
            yield name, off, body
        off += 60 + size + (size & 1)


def parse_coff(name, off, body):
    f_magic, f_nscns = struct.unpack(">HH", body[0:4])
    if f_magic != 0x0500:
        raise ValueError(f"{name}: unexpected COFF magic 0x{f_magic:04x}")
    f_opthdr, = struct.unpack(">H", body[16:18])
    mod = Module(name=name, offset=off)
    base = 20 + f_opthdr
    for i in range(f_nscns):
        sh = body[base + 40 * i: base + 40 * (i + 1)]
        sname = sh[0:8].split(b"\0")[0].decode("ascii", "replace")
        size, scnptr, relptr = struct.unpack(">III", sh[16:28])
        nreloc, = struct.unpack(">H", sh[32:34])
        flags, = struct.unpack(">I", sh[36:40])
        if size == 0:
            continue
        is_bss = bool(flags & 0x80)
        raw = b"" if is_bss else body[scnptr:scnptr + size]
        s = Section(name=sname, length=size,
                    contents=0 if (flags & 0x20) else 0x10,  # STYP_TEXT
                    data=raw if raw else bytes(size),
                    covered=b"\x01" * size if raw else b"\x00" * size)
        for r in range(nreloc):
            entry = body[relptr + 10 * r: relptr + 10 * r + 10]
            vaddr, _symndx = struct.unpack(">II", entry[0:8])
            rtype, = struct.unpack(">H", entry[8:10])
            s.reloc_holes.append((vaddr, 4, rtype, None))
        mod.sections.append(s)
    return mod


def modules(path):
    for name, off, body in ar_members(path):
        if len(body) < 4 or struct.unpack(">H", body[0:2])[0] != 0x0500:
            continue  # non-object member (headers, docs) — not scannable
        yield parse_coff(name, off, body)
