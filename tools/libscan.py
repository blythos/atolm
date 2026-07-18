#!/usr/bin/env python3
"""Scan a PRG for placements of SYSROF library members (Bucket 3 deliverable 1).

For every code section of every module in the given .LIB/.OBJ files, builds a
(bytes, mask) fingerprint via tools/sysrof.py — relocation holes and
never-emitted filler are wildcards — and searches the target binary for
placements where every fixed byte matches.

Search: the longest fixed-byte run of the fingerprint is used as a find()
anchor; each anchor hit is verified against the full mask. Placements are
required to be 2-byte aligned (SH2). Members whose fixed-byte count is below
--min-fixed are reported as too-small-to-fingerprint, never claimed.

Output TSV columns:
  lib  member  tool  section  sec_len  fixed_bytes  status  placements
where placements is a comma-separated list of file offsets (hex), and status
is one of: hit-1 (unique), hit-N (multiple), miss, too-small.
Nothing here writes to the repo; results are printed for review.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coffar
import sysrof


def load_modules(path):
    """Dispatch on container format: ar (.A, GNU sh-coff) or SYSROF (.LIB/.OBJ)."""
    with open(path, "rb") as f:
        magic = f.read(8)
    if magic == b"!<arch>\n":
        return coffar.modules(path)
    return sysrof.modules(path)


def longest_fixed_run(mask):
    best = (0, 0)  # (length, start)
    cur_start = None
    for i, b in enumerate(mask):
        if b and cur_start is None:
            cur_start = i
        elif not b and cur_start is not None:
            best = max(best, (i - cur_start, cur_start))
            cur_start = None
    if cur_start is not None:
        best = max(best, (len(mask) - cur_start, cur_start))
    return best[1], best[0]  # start, length


def masked_match(target, pos, data, mask):
    if pos < 0 or pos + len(data) > len(target):
        return False
    for i in range(len(data)):
        if mask[i] and target[pos + i] != data[i]:
            return False
    return True


def find_placements(target, data, mask, align=2):
    astart, alen = longest_fixed_run(mask)
    anchor = data[astart:astart + alen]
    hits = []
    j = target.find(anchor)
    while j != -1:
        pos = j - astart
        if pos % align == 0 and masked_match(target, pos, data, mask):
            hits.append(pos)
        j = target.find(anchor, j + 1)
    return hits


def scan(target, libpaths, min_fixed=16, which="code"):
    """Return result rows: (lib, mod, tool, sect, len, fixed, hits, ext_defs)."""
    rows = []
    for path in libpaths:
        lib = os.path.basename(path)
        for mod in load_modules(path):
            code_idx = [i for i, s in enumerate(mod.sections)
                        if s.contents == 0 and s.length > 0]
            sects = (mod.sections if which == "all"
                     else sysrof.code_sections(mod))
            for s in sects:
                if s.length == 0 or not any(s.covered):
                    continue
                data, mask = sysrof.section_image(s)
                fixed = sum(1 for b in mask if b)
                if fixed < min_fixed:
                    hits, status = [], "too-small"
                else:
                    hits = find_placements(target, data, mask)
                    status = f"hit-{len(hits)}" if hits else "miss"
                # exported symbols inside this section (code sections only)
                sidx = mod.sections.index(s)
                syms = sorted(
                    (a, n) for (sect, a, n, _t) in getattr(mod, "ext_defs", [])
                    if sect == sidx and sect in code_idx)
                rows.append(dict(lib=lib, member=mod.name, tool=mod.tool,
                                 section=s.name, length=s.length, fixed=fixed,
                                 status=status, hits=hits, syms=syms))
    return rows


def emit_tsv(rows):
    print("lib\tmember\ttool\tsection\tsec_len\tfixed\tstatus\tplacements")
    for r in rows:
        ph = ",".join(f"0x{h:05x}" for h in r["hits"])
        print(f"{r['lib']}\t{r['member']}\t{r['tool']}\t{r['section']}"
              f"\t{r['length']}\t{r['fixed']}\t{r['status']}\t{ph}")


def emit_yaml(rows, target, pad_limit=8):
    """Print manifest segment rows for unique hits, contiguous runs merged;
    link pads up to pad_limit bytes are folded into the preceding row.
    All hashes are computed here, from the target bytes (charter §5 rule)."""
    import hashlib
    hits = sorted(((r["hits"][0], r) for r in rows if r["status"] == "hit-1"),
                  key=lambda t: t[0])
    i = 0
    while i < len(hits):
        pos, r = hits[i]
        end = pos + r["length"]
        pad = 0
        if i + 1 < len(hits):
            nxt = hits[i + 1][0]
            if end < nxt <= end + pad_limit:
                pad = nxt - end
                end = nxt
        h = hashlib.sha256(target[pos:end]).hexdigest()
        note = f" (+{pad} link-pad bytes)" if pad else ""
        twins = [r2 for p2, r2 in hits
                 if p2 == pos and r2 is not r]
        twin = (f"; byte-identical twin: "
                + ",".join(f"{t['lib']}/{t['member']}" for t in twins)
                if twins else "")
        print(f"  - start: 0x{pos:05x}\n    end: 0x{end:05x}\n"
              f"    state: library-identified\n"
              f"    member: {r['lib']}/{r['member']}\n"
              f"    evidence: >-\n"
              f"      Bucket 3 fingerprint scan (tools/libscan.py): "
              f"{r['fixed']}/{r['length']} fixed bytes of {r['section']} "
              f"exact at unique placement, translator {r['tool']}{note}{twin}\n"
              f"    sha256: {h}")
        # skip any twin rows at the same placement
        while i + 1 < len(hits) and hits[i + 1][0] == pos:
            i += 1
        i += 1


def emit_symbols(rows, vma_base):
    """Print symbols-file rows for unique hits' exported code symbols."""
    seen = set()
    for r in sorted(rows, key=lambda r: r["hits"][0] if r["hits"] else 0):
        if r["status"] != "hit-1":
            continue
        pos = r["hits"][0]
        for off, name in r["syms"]:
            vma = vma_base + pos + off
            if vma in seen:
                continue
            seen.add(vma)
            print(f"0x{vma:08x} {name.lstrip('_')} verified  "
                  f"# {r['lib']}/{r['member']}+0x{off:x}, library-identified")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="binary to scan (e.g. extracted/1ST_READ.PRG)")
    ap.add_argument("libs", nargs="+", help=".LIB/.OBJ/.A files")
    ap.add_argument("--min-fixed", type=int, default=16,
                    help="minimum fixed bytes to attempt identification")
    ap.add_argument("--sections", choices=["code", "all"], default="code",
                    help="which member sections to scan")
    ap.add_argument("--emit", choices=["tsv", "yaml", "symbols"], default="tsv")
    ap.add_argument("--vma-base", type=lambda x: int(x, 0), default=0x06006000)
    args = ap.parse_args()

    target = open(args.target, "rb").read()
    rows = scan(target, args.libs, args.min_fixed, args.sections)
    print(f"# tools/libscan.py --emit {args.emit} {args.target} "
          f"({len(target)} bytes), {len(args.libs)} lib files")
    if args.emit == "tsv":
        emit_tsv(rows)
    elif args.emit == "yaml":
        emit_yaml(rows, target)
    else:
        emit_symbols(rows, args.vma_base)


if __name__ == "__main__":
    main()
