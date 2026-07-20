#!/usr/bin/env python3
"""Scoped source permuter (Bucket 4 STOP 2) — the "cheap tier".

Searches semantics-preserving source variants for a byte match, scoped to the
schedule (#3) / register (#4) drift families. Rather than mutate an AST blindly
(decomp-permuter's job, the expensive tier), the reconstructor marks the
alternatives it believes bracket the residual, as inline directives:

    /*PERM sum+=t*w; | sum+=w*t; */        (choose one of the alternatives)

permute expands the cross-product of all PERM sites (bounded by --budget),
compiles each variant with the canonical flags, and byte-scores the target
against the extracted original. Leaf targets (no bsr/pool) are compiled in one
batch for speed; otherwise each variant compiles as a whole unit.

Usage:
  # leaf: target bytes given directly, all variants batched
  python3 tools/permute.py --src FILE --fn NAME --target-hex HEX
  # in-unit member: score member VMA within the unit seeded at --seed
  python3 tools/permute.py --src FILE --seed VMA --member VMA

On an exact match, prints the winning variant and writes it next to --src as
<src>.matched. Otherwise prints the best diff and confirms the search budget.

INTEGRITY CAVEAT (Bucket 4 STOP 2): SHC codegen is translation-unit-context-
dependent (docs/FINDINGS/1ST_READ_tu_position_dependence.md) — a function's
bytes depend on the functions preceding it in the TU. In batch leaf mode each
variant sits at a different position, so an "EXACT" here means "this source at
this batch position matches" and is NOT a standalone proof. Every match this
tool proposes MUST be confirmed at the intended reconstructed configuration via
tools/try_match.sh (single function) or tools/tu_build.py (in a unit), which
compare against the extracted original. try_match is the authority (charter §5).
"""
import argparse
import itertools
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prg import REPO

VMA_BASE = 0x06006000
CANON = "-optimize=1 -speed -macsave=0"
PERM = re.compile(r"/\*PERM\s+(.*?)\*/", re.S)


def expand(src):
    """Yield (variant_source, choices) for the cross-product of PERM sites."""
    sites = PERM.findall(src)
    if not sites:
        yield src, ()
        return
    options = [[a.strip() for a in s.split("|")] for s in sites]
    parts = PERM.split(src)          # text, opt, text, opt, ... text
    for combo in itertools.product(*options):
        out = parts[0]
        for i, choice in enumerate(combo):
            out += choice + parts[2 + i * 2]
        yield out, combo


def container_compile(workdir, srctext, flags):
    os.makedirs(workdir, exist_ok=True)
    open(os.path.join(workdir, "UNIT.C"), "w").write(srctext)
    subprocess.run([os.path.join(REPO, "toolchain/shc/run.sh"), workdir,
                    f"shc-compile UNIT.C p {flags}"],
                   capture_output=True, text=True)
    b = os.path.join(workdir, "p.bin")
    return open(b, "rb").read() if os.path.exists(b) else None


def text_syms(workdir):
    st = subprocess.run([os.path.join(REPO, "tools/sh-elf.sh"), workdir,
                         "objdump", "-t", "p.elf"],
                        capture_output=True, text=True).stdout
    syms = {}
    for line in st.splitlines():
        p = line.split()
        if len(p) >= 6 and ".text" in p and p[2] == "F":
            try:
                syms[p[-1].lstrip("_")] = int(p[0], 16)
            except ValueError:
                pass
    return syms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--fn", help="leaf function name (batch/standalone mode)")
    ap.add_argument("--target-hex", help="target bytes for --fn")
    ap.add_argument("--seed", help="unit seed VMA (in-unit mode)")
    ap.add_argument("--member", help="target member VMA (in-unit mode)")
    ap.add_argument("--flags", default=CANON)
    ap.add_argument("--budget", type=int, default=512)
    args = ap.parse_args()

    base = open(os.path.join(REPO, args.src)).read()
    variants = list(itertools.islice(expand(base), args.budget))
    total_sites = len(PERM.findall(base))
    work = os.path.join(REPO, "build/permute")
    os.makedirs(work, exist_ok=True)

    if args.fn and args.target_hex:
        target = bytes.fromhex(args.target_hex.replace(" ", ""))
        # batch: emit every variant's fn under a unique name into one file
        renamed, names = [], []
        for i, (v, _) in enumerate(variants):
            nm = f"{args.fn}_{i}"
            names.append(nm)
            renamed.append(re.sub(rf"\b{re.escape(args.fn)}\b", nm, v, count=1))
        blob = container_compile(work, "\n".join(renamed), args.flags)
        if blob is None:
            print("COMPILE ERROR (batch)"); sys.exit(2)
        syms = text_syms(work)
        order = sorted(((off, nm) for nm, off in syms.items()),
                       key=lambda x: x[0])
        best = (10 ** 9, None)
        exact = []
        for j, (off, nm) in enumerate(order):
            end = order[j + 1][0] if j + 1 < len(order) else len(blob)
            b = blob[off:end]
            d = abs(len(b) - len(target)) + sum(x != y
                                                for x, y in zip(b, target))
            if b == target:
                exact.append(nm)
            if d < best[0]:
                best = (d, nm)
        print(f"permute {args.fn}: {len(variants)} variants "
              f"({total_sites} PERM sites), budget {args.budget}")
        print(f"  EXACT: {exact if exact else 'none'}")
        print(f"  best diff {best[0]} ({best[1]})")
        if exact:
            idx = int(exact[0].rsplit("_", 1)[1])
            open(os.path.join(REPO, args.src + ".matched"), "w").write(
                variants[idx][0])
            print(f"  winning source -> {args.src}.matched")
        sys.exit(0 if exact else 1)

    # in-unit mode
    import tu_cluster
    insn, starts, poolw, endfile = tu_cluster.load()
    seed = int(args.seed, 16)
    members, lo, hi = tu_cluster.minimal_unit(seed, insn, starts, endfile)
    mem = int(args.member, 16)
    sizes = [tu_cluster.flow_extent(m, insn) - m for m in members]
    moff = sum(sz for m, sz in zip(members, sizes) if m < mem)
    msize = sizes[members.index(mem)]
    prg = open(os.path.join(REPO, "extracted/1ST_READ.PRG"), "rb").read()
    target = prg[lo - VMA_BASE: hi - VMA_BASE][moff:moff + msize]
    best = (10 ** 9, None)
    exact = []
    for i, (v, combo) in enumerate(variants):
        blob = container_compile(work, v, args.flags)
        if blob is None:
            continue
        b = blob[moff:moff + msize]
        d = abs(len(b) - len(target)) + sum(x != y for x, y in zip(b, target))
        if b == target and len(blob) == (hi - lo):
            exact.append(i)
        if d < best[0]:
            best = (d, i)
    print(f"permute member 0x{mem:07x} in unit 0x{lo:07x}: "
          f"{len(variants)} variants ({total_sites} PERM sites)")
    print(f"  EXACT: {[str(e) for e in exact] if exact else 'none'}  "
          f"best diff {best[0]} (variant {best[1]})")
    if exact:
        open(os.path.join(REPO, args.src + ".matched"), "w").write(
            variants[exact[0]][0])
        print(f"  winning source -> {args.src}.matched")
    sys.exit(0 if exact else 1)


if __name__ == "__main__":
    main()
