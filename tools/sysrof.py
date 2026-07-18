#!/usr/bin/env python3
"""Hitachi SYSROF object/library reader (read-only, for library identification).

Parses the SYSROF relocatable-object format used by Hitachi SHC-era tools
(SEGA_*.LIB / SYS_*.OBJ on the Sega Saturn dev discs) far enough to recover,
per library member: unit name, translator tag, section list, section byte
images, and relocation holes. No Sega bytes are emitted by this module; it
reads gitignored reference/ inputs only.

Format knowledge derived empirically (Bucket 3) from SYSDUMP.EXE output
(the SDTK's own period tool, run under dosemu in Bucket 0.6b) paired with
the raw library bytes; the parser is validated byte-exact against the 58
P-section extractions sysdump produced in 0.6b (see docs/FINDINGS).

Record layout: [type][len][payload...][checksum]  (len = total record length
including type/len/checksum; len is a plain byte, 0xff = 255 literally —
long data is split across multiple ob records of <=246 data bytes).
The type byte's low 7 bits select the record kind (sysdump's labels):
  0x00 cs   contents summary          0x14 ed   external definitions
  0x04 hd   module header             0x1a sh   section switch (unit, sect)
  0x06 un   unit header               0x1c ob   object data
  0x08 sc   section definition        0x20 rl   relocation entries
  0x0c er   external references       0x7f tr   terminator
Library containers (P032LBR1): 0x60 lib header, 0x62 module directory,
0x64 public-symbol directory, blocks zero/junk-padded to 0x100 boundaries;
members start at the module-start record 80 21 00 80 (cs).
"""
import struct
import sys
from dataclasses import dataclass, field

MODULE_MAGIC = b"\x80\x21\x00\x80"


@dataclass
class Section:
    name: str
    length: int
    align: int
    contents: int  # 0 = code
    # byte image and hole mask, both length `length`
    data: bytearray = field(default_factory=bytearray)
    covered: bytearray = field(default_factory=bytearray)  # 1 = emitted by an ob record
    reloc_holes: list = field(default_factory=list)  # (offset, nbytes, op, symn)


@dataclass
class Module:
    name: str = ""
    tool: str = ""       # translator tag, e.g. C_SH970707174715
    sections: list = field(default_factory=list)
    ext_refs: list = field(default_factory=list)
    ext_defs: list = field(default_factory=list)   # (section_idx, address, name)
    offset: int = 0      # byte offset of the module inside the container file


def records(data, start, end):
    """Yield (kind, payload) for SYSROF records in data[start:end].

    Payload excludes type/len/checksum. Stops at the tr record or end.
    """
    off = start
    while off < end - 1:
        t = data[off]
        ln = data[off + 1]
        payload = data[off + 2:off + ln - 1]
        kind = t & 0x7F
        yield kind, payload
        if kind == 0x7F:  # tr
            return
        if ln < 2:
            raise ValueError(f"bad record length {ln} at 0x{off:x}")
        off += ln


def _counted_names(buf):
    """Parse sequences of [flags?][len][name] used in er records: c0 0d name..."""
    names, i = [], 0
    while i < len(buf):
        # er entry: 1 type byte (0xc0|sym type) + len + name
        ln = buf[i + 1]
        names.append(buf[i + 2:i + 2 + ln].decode("ascii", "replace"))
        i += 2 + ln
    return names


def _ed_entries(buf):
    """ed record: entries of [section:2][type:1][address][len][name].

    The address field is 4 bytes, except when type bit 0x40 is set (absolute
    symbols, e.g. SGL's work-RAM cells): then an explicit size byte precedes
    a size-byte-wide address. Types observed: 0x00 code entry, 0x20 data
    object, 0x40|x absolute. Entries never straddle record boundaries.
    """
    out, i = [], 0
    while i + 8 <= len(buf):
        sect, = struct.unpack(">H", buf[i:i + 2])
        typ = buf[i + 2]
        i += 3
        if typ & 0x40:
            asz = buf[i]
            addr = int.from_bytes(buf[i + 1:i + 1 + asz], "big")
            i += 1 + asz
        else:
            addr, = struct.unpack(">I", buf[i:i + 4])
            i += 4
        ln = buf[i]
        name = buf[i + 1:i + 1 + ln].decode("ascii", "replace")
        i += 1 + ln
        out.append((sect, addr, name, typ))
    return out


def parse_module(data, start, end):
    """Parse one SYSROF module from data[start:end] (start at MODULE_MAGIC)."""
    mod = Module(offset=start)
    cur_sect = None
    for kind, p in records(data, start, end):
        if kind == 0x04:  # hd — module name lives near the end: [nlen][name][clen][cpu]
            # layout: mt,spare, cd(12 ascii), nu:2, code, ver(4 ascii), au, si,
            # afl, spare, spcsz, segsz, segsh, ep..., then counted os, sys, mn, cpu
            # Parse from the tail: it is [len]name[len]cpu with cpu last.
            # Walk counted strings from a known fixed prefix instead: the fixed
            # part is 1+1+12+2+1+4+1+1+1+1+1+... — varies; take module name from
            # the un record instead (same value).
            pass
        elif kind == 0x06:  # un: format,spare, nsect:1, nref:2, ndef:2, [n]name [n]tool [tcd:12]...
            nsect = p[2]
            nref, ndef = struct.unpack(">HH", p[3:7])
            i = 7
            ln = p[i]; mod.name = p[i + 1:i + 1 + ln].decode("ascii", "replace"); i += 1 + ln
            ln = p[i]; mod.tool = p[i + 1:i + 1 + ln].decode("ascii", "replace"); i += 1 + ln
        elif kind == 0x08:  # sc: fmt, spare, segadd:4?, addr.., length:4, align, contents.., [n]name
            # observed payload: 40 00 | 00 00 00 | 00 00 01 28 | 00 00 00 04 |
            #                   00 ff c0 | 06 'SEGA_P'   (length at [5:9])
            length, = struct.unpack(">I", p[5:9])
            align, = struct.unpack(">I", p[9:13])
            contents = p[13]  # 0x00 = code, 0x10 = const data (attr bytes p[13:16])
            nlen = p[16]
            name = p[17:17 + nlen].decode("ascii", "replace")
            s = Section(name=name, length=length, align=align, contents=contents)
            s.data = bytearray(length)
            s.covered = bytearray(length)
            mod.sections.append(s)
        elif kind == 0x0C:  # er
            mod.ext_refs.extend(_counted_names(p))
        elif kind == 0x14:  # ed
            mod.ext_defs.extend(_ed_entries(p))
        elif kind == 0x1A:  # sh: unit:2, section:2
            sect_idx, = struct.unpack(">H", p[2:4])
            cur_sect = mod.sections[sect_idx]
        elif kind == 0x1C:  # ob
            flags = p[0]
            addr, = struct.unpack(">I", p[1:5])
            if flags & 0x40:  # compressed: [reps:4][datalen][pattern]
                reps, = struct.unpack(">I", p[5:9])
                dlen = p[9]
                blob = bytes(p[10:10 + dlen]) * reps
            else:
                dlen = p[5]
                blob = bytes(p[6:6 + dlen])
                if dlen != len(blob):
                    raise ValueError(f"short ob record in {mod.name}")
            if cur_sect is None:
                raise ValueError(f"ob before sh in {mod.name}")
            cur_sect.data[addr:addr + len(blob)] = blob
            for k in range(addr, addr + len(blob)):
                cur_sect.covered[k] = 1
        elif kind == 0x20:  # rl: variable-length entries
            # [flags][spare:2][addr:2][bitloc][flen][bcount][expr... 0xff]
            # flags>>2 = 1-based appearance number of the section holding the
            # hole; bcount = length of the RPN reloc expression incl. its 0xff
            # terminator (C modules emit the 4-byte OP_EXT_REF form, assembly
            # modules longer chains — semantics irrelevant for wildcarding).
            i = 0
            while i + 8 <= len(p):
                segment = p[i] >> 2
                addr, = struct.unpack(">H", p[i + 3:i + 5])
                flen = p[i + 6]
                bcount = p[i + 7]
                expr = p[i + 8:i + 8 + bcount]
                if len(expr) != bcount or expr[-1] != 0xFF:
                    raise ValueError(
                        f"bad rl expression in {mod.name} at entry offset {i}: "
                        f"{p[i:i + 8 + bcount].hex()}")
                op = expr[0]
                # Holes land in the CURRENT section (the last sh record's),
                # like ob records; the entry's segment field describes the
                # relocation target, not the hole location. Verified on C
                # modules (single section), fld_load (P holes before the C
                # sh), and sgli00 (holes inside SLPROG, an empty P present).
                if cur_sect is None:
                    raise ValueError(f"rl before sh in {mod.name}")
                if addr + flen // 8 > cur_sect.length:
                    raise ValueError(
                        f"rl addr 0x{addr:x} beyond {cur_sect.name} in {mod.name}")
                cur_sect.reloc_holes.append((addr, flen // 8, op, segment))
                i += 8 + bcount
    return mod


def modules(path):
    """Yield Module for every SYSROF module in a .LIB container or bare .OBJ."""
    data = open(path, "rb").read()
    starts = []
    i = data.find(MODULE_MAGIC)
    while i != -1:
        starts.append(i)
        i = data.find(MODULE_MAGIC, i + 1)
    for n, s in enumerate(starts):
        e = starts[n + 1] if n + 1 < len(starts) else len(data)
        yield parse_module(data, s, e)


def section_image(sect):
    """Return (bytes, mask) for a section; mask byte 1 = fixed/comparable,
    0 = wildcard (relocation hole or never-emitted filler)."""
    mask = bytearray(sect.covered)
    for off, nbytes, _op, _seg in sect.reloc_holes:
        for k in range(off, min(off + nbytes, len(mask))):
            mask[k] = 0
    return bytes(sect.data), bytes(mask)


def code_sections(mod):
    """Sections carrying code bytes (attr 0x00, nonzero length, data emitted)."""
    return [s for s in mod.sections
            if s.contents == 0 and s.length > 0 and any(s.covered)]


def p_section(mod):
    """(bytes, mask) of the module's primary code section, or (None, None)."""
    cs = code_sections(mod)
    if not cs:
        return None, None
    best = max(cs, key=lambda s: s.length)
    return section_image(best)


if __name__ == "__main__":
    for path in sys.argv[1:]:
        for m in modules(path):
            p, mask = p_section(m)
            secs = ", ".join(f"{s.name}:{s.length}" for s in m.sections)
            nrel = sum(len(s.reloc_holes) for s in m.sections)
            wc = mask.count(0) if mask else 0
            print(f"{path}\t{m.name}\t{m.tool}\t[{secs}]\trelocs={nrel}"
                  f"\tP_wildcards={wc}")
