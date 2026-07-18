#!/usr/bin/env python3
"""Function/data mapper for SH-2 PRG targets (Bucket 2).

Reads an objdump disassembly of the extracted binary (generated locally in
the SHC container — see disasm()) and produces a function inventory +
literal-pool map + code/data classification, iterated to a fixpoint so that
literal-pool words decoded as fake instructions (FINDINGS gotcha) cannot
seed bogus prologues or call targets.

Function starts come from four evidence chains, each recorded per function:
  entry     — the load address itself (nothing calls the entry point)
  prologue  — first push of a callee-save run (descending = SHC idiom,
              ascending = GCC pocket) or a bare sts.l pr,@-r15
  bsr/jsr-pool — target of a bsr, or of a jsr/jmp @rn whose rn provably
              comes from a nearby PC-relative pool load (catches leaf
              functions with no saves, which prologue scanning misses)
  ptr32     — a 4-aligned BE32 word anywhere in the file holds this
              address (function-pointer table), AND the address is
              preceded by a function terminator (rts/bra/jmp/rte + delay
              slot) or pool bytes — the precondition rejects switch-table
              targets, which are mid-flow
  ghidra    — merged in later by tools/ghidra_reconcile.py, not this script

Output JSON (build/analysis/<target>.map.json) is disc-derived (pool
values) and stays gitignored; the committed segments map in config/ is
distilled from it with offsets/sizes/states/hashes only.

Usage: python3 tools/sh2_map.py 1ST_READ.PRG
"""
import bisect
import json
import os
import re
import subprocess
import sys

from prg import REPO, load_manifests

LINE = re.compile(
    r"^\s*([0-9a-f]+):\s+([0-9a-f]{2} [0-9a-f]{2})\s+(\S+)\s*(.*?)\s*$")
POOL_LOAD = re.compile(r"^0x([0-9a-f]+),(r\d+)\s+!\s*([0-9a-f]+)")
PUSH = re.compile(r"^(r\d+),@-r15")


def disasm(target, extracted, vma_base):
    """Disassemble the extracted binary in the SHC container (sh-elf
    binutils live there, not on the host). Output lands in build/analysis/."""
    workdir = os.path.join(REPO, "build/analysis")
    os.makedirs(workdir, exist_ok=True)
    out = os.path.join(workdir, f"{target}.disasm.txt")
    if not os.path.exists(out) or (os.path.getmtime(out) <
                                   os.path.getmtime(extracted)):
        sub = os.path.join(workdir, target)
        with open(extracted, "rb") as f, open(sub, "wb") as g:
            g.write(f.read())
        subprocess.run(
            [os.path.join(REPO, "toolchain/shc/run.sh"), workdir,
             f"sh-elf-objdump -D -b binary -m sh2 -EB "
             f"--adjust-vma={vma_base:#x} /work/{target} "
             f"> /work/{target}.disasm.txt"],
            check=True, capture_output=True)
    return out


def parse(path):
    """[(addr, mnemonic, operands)] for every 16-bit word objdump printed."""
    insns = []
    with open(path) as f:
        for line in f:
            m = LINE.match(line)
            if m:
                insns.append((int(m.group(1), 16), m.group(3), m.group(4)))
    return insns


class Mapper:
    def __init__(self, insns, vma_base, size):
        self.insns = insns
        self.index = {a: i for i, (a, _, _) in enumerate(insns)}
        self.vma_base = vma_base
        self.end = vma_base + size
        self.pool = {}          # addr -> width (2 or 4) of pool slots
        self.pool_values = {}   # addr -> long value (mov.l loads only)

    def in_range(self, a):
        return self.vma_base <= a < self.end

    def is_pool(self, a):
        return a in self.pool or (a - 2) in self.pool and \
            self.pool.get(a - 2) == 4

    def scan(self):
        """One pass over non-pool instructions. Returns (prologues,
        call_targets, pool_refs) discovered this pass."""
        prologues = []
        call_targets = {}       # addr -> evidence string
        pool_refs = {}          # addr -> (width, value_or_None)
        recent_loads = {}       # reg -> (value, insn_idx) for jsr resolution
        prev_push_reg = None    # register pushed by the previous instruction
        prev_addr = None
        for i, (addr, mnem, ops) in enumerate(self.insns):
            if self.is_pool(addr):
                prev_push_reg = None
                recent_loads.clear()
                prev_addr = None
                continue
            # discontinuity (pool carved out between insns) resets context
            if prev_addr is not None and addr - prev_addr > 2:
                prev_push_reg = None
                recent_loads.clear()
            prev_addr = addr
            pushed = None

            m = POOL_LOAD.match(ops) if mnem in ("mov.l", "mov.w") else None
            if m:
                pa, reg, val = (int(m.group(1), 16), m.group(2),
                                int(m.group(3), 16))
                width = 4 if mnem == "mov.l" else 2
                pool_refs[pa] = (width, val if mnem == "mov.l" else None)
                recent_loads[reg] = (val if mnem == "mov.l" else None, i)
            elif mnem == "mov.l" and PUSH.match(ops):
                reg = int(PUSH.match(ops).group(1)[1:])
                if prev_push_reg is None:
                    prologues.append((addr, reg))
                pushed = reg
            elif mnem == "sts.l" and ops == "pr,@-r15":
                if prev_push_reg is None:
                    prologues.append((addr, "pr"))
            elif mnem == "bsr":
                t = int(ops.replace("0x", ""), 16)
                if self.in_range(t):
                    call_targets[t] = "bsr"
            elif mnem in ("jsr", "jmp") and ops.startswith("@r"):
                reg = ops[1:]
                if reg in recent_loads:
                    val, idx = recent_loads[reg]
                    if val is not None and self.in_range(val) \
                            and i - idx <= 24:
                        call_targets[val] = f"{mnem}-pool"
            else:
                # a write to a register invalidates its tracked pool load
                dst = re.search(r",(r\d+)$", ops)
                if dst and dst.group(1) in recent_loads:
                    del recent_loads[dst.group(1)]
            prev_push_reg = pushed
        return prologues, call_targets, pool_refs

    def run(self):
        """Iterate scan + pool exclusion to fixpoint."""
        passes = 0
        while True:
            passes += 1
            prologues, call_targets, pool_refs = self.scan()
            new = {a: w for a, (w, _) in pool_refs.items()
                   if self.in_range(a) and a not in self.pool}
            for a, (w, v) in pool_refs.items():
                if v is not None:
                    self.pool_values[a] = v
            if not new or passes > 8:
                break
            self.pool.update(new)
        self.prologues = prologues
        self.call_targets = call_targets
        self.passes = passes
        return passes


TERMINATORS = ("rts", "bra", "jmp", "rte")


def ptr32_starts(data, vma_base, insn_by_addr, pool):
    """Function-pointer-table evidence: 4-aligned BE32 words holding an
    in-range even address whose site looks like a function START (preceded
    by terminator+delay or by pool bytes). Rejects switch-table targets."""
    import struct
    end = vma_base + len(data)
    hits = set()
    for off in range(0, len(data) - 3, 4):
        v = struct.unpack_from(">I", data, off)[0]
        if not (vma_base <= v < end) or v % 2:
            continue
        prev = insn_by_addr.get(v - 4)
        if (v - 2) in pool or (v - 4) in pool or v == vma_base:
            hits.add(v)
        elif prev is not None and prev[1] in TERMINATORS:
            hits.add(v)
    return hits


def main():
    target_name = sys.argv[1] if len(sys.argv) > 1 else "1ST_READ.PRG"
    m = next(x for x in load_manifests() if x["target"] == target_name)
    vma_base, size = m["vma_base"], m["size"]
    extracted = os.path.join(REPO, "extracted", target_name)
    if not os.path.exists(extracted):
        sys.exit(f"sh2_map: extracted/{target_name} missing — make extract")

    insns = parse(disasm(target_name, extracted, vma_base))
    mapper = Mapper(insns, vma_base, size)
    mapper.run()

    # function starts: prologue hits + call targets not inside pools,
    # 2-byte aligned, in range
    starts = {}
    starts[vma_base] = {"evidence": ["entry"]}
    for addr, reg in mapper.prologues:
        starts.setdefault(addr, {"evidence": []})
        starts[addr]["evidence"].append("prologue")
        starts[addr]["first_push"] = str(reg)
    for addr, ev in mapper.call_targets.items():
        if mapper.is_pool(addr):
            continue
        starts.setdefault(addr, {"evidence": []})["evidence"].append(ev)
    with open(extracted, "rb") as f:
        data = f.read()
    insn_by_addr = {a: (a, mn, op) for a, mn, op in mapper.insns}
    for addr in ptr32_starts(data, vma_base, insn_by_addr, mapper.pool):
        if not mapper.is_pool(addr):
            starts.setdefault(addr, {"evidence": []})["evidence"].append(
                "ptr32")

    out = {
        "target": target_name,
        "vma_base": vma_base,
        "size": size,
        "fixpoint_passes": mapper.passes,
        "instruction_words": len(insns),
        "pool_slots": len(mapper.pool),
        "pool_bytes": sum(mapper.pool.values()),
        "functions": [
            {"vma": a, **starts[a]} for a in sorted(starts)],
        "pool_addrs": sorted(mapper.pool),
        "pool_widths": {f"{a:#x}": w for a, w in sorted(mapper.pool.items())},
        "pool_values": {f"{a:#x}": v
                        for a, v in sorted(mapper.pool_values.items())},
    }
    dest = os.path.join(REPO, "build/analysis", f"{target_name}.map.json")
    with open(dest, "w") as f:
        json.dump(out, f, indent=1)
    ev_count = {}
    for s in starts.values():
        for e in s["evidence"]:
            ev_count[e] = ev_count.get(e, 0) + 1
    print(f"sh2_map: {target_name}: {len(starts)} function starts "
          f"(evidence: {ev_count}), "
          f"{len(mapper.pool)} pool slots ({out['pool_bytes']} bytes), "
          f"fixpoint in {mapper.passes} passes -> {dest}")


if __name__ == "__main__":
    main()
