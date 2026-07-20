#!/usr/bin/env python3
"""A/B/C matchability classifier (Bucket 4 STOP 2.5) — MEASUREMENT ONLY.

Reachability measurement for the three-way matchability split forced by the
STOP-2 TU-position-dependence finding
(docs/FINDINGS/1ST_READ_tu_position_dependence.md):

  A = shipped bytes reproduced in isolation (position-robust);
  B = not isolated, but reproduced under SOME translation-unit context
      (proves R31 CAN emit the shipped bytes — reachable);
  C = reproduced under no context in the battery (candidate version-blocked).

This is NOT a matching tool and NOT the context/position permuter (whose
adoption is the STOP-3 decision). It only measures which class a function falls
in, to size those populations. A/B are self-validating (assigned only on an
actual byte match, so the reconstruction is proven correct); a C is reported
only when the isolated compile's instruction multiset already matches the
target (else the reconstruction is flagged incomplete, not called C).

Context is sampled by realizing many TU positions in one compile: the target
function repeated behind growing, varied padding functions.

Reproduce the STOP-2.5 sample: python3 tools/classify_abc.py
Classify your own: pass a JSON file {name: [target_hex, [c_source_shapes...]]}
where each shape defines a function named T. Slow (many container compiles).
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prg import REPO

WORK = os.path.join(REPO, "build/classify")
FLAGS = "-optimize=1 -speed -macsave=0"
PADSETS = [
    ["int P{n}(a)int a;{{return a;}}"],
    ["int P{n}(a,b)int a,b;{{return a*b;}}"],
    ["int P{n}(p)int*p;{{int s=0,k;for(k=0;k<4;k++)s+=p[k];return s;}}"],
    ["void P{n}(p,m)char*p;int m;{{do{{*p++=0;}}while(--m);}}"],
    ["int P{n}(a,b,c,d)int a,b,c,d;{{return a*b+c*d;}}"],
]


def _compile(src):
    os.makedirs(WORK, exist_ok=True)
    open(os.path.join(WORK, "UNIT.C"), "w").write(src)
    subprocess.run([os.path.join(REPO, "toolchain/shc/run.sh"), WORK,
                    f"shc-compile UNIT.C c {FLAGS}"], capture_output=True)
    b = os.path.join(WORK, "c.bin")
    if not os.path.exists(b):
        return None, None
    st = subprocess.run([os.path.join(REPO, "tools/sh-elf.sh"), WORK,
                         "objdump", "-t", "c.elf"], capture_output=True,
                        text=True).stdout
    syms = {}
    for line in st.splitlines():
        p = line.split()
        if len(p) >= 6 and ".text" in p and p[2] == "F":
            try:
                syms[p[-1].lstrip("_")] = int(p[0], 16)
            except ValueError:
                pass
    return open(b, "rb").read(), syms


def _slice(blob, syms, name):
    order = sorted(syms.items(), key=lambda kv: kv[1])
    for j, (nm, off) in enumerate(order):
        if nm == name:
            end = order[j + 1][1] if j + 1 < len(order) else len(blob)
            return blob[off:end]
    return None


def _itypes(hx):
    """register-agnostic instruction-class multiset (for the C validity gate)."""
    out = []
    for i in range(0, len(hx), 4):
        w = int(hx[i:i + 4], 16)
        top = w >> 12
        if top in (0x6, 0x2, 0x3, 0x5, 0x1):
            out.append((top, w & 0x000f))
        elif top == 0x4:
            out.append((top, w & 0x00ff))
        else:
            out.append((top,))
    return sorted(out)


def classify(shapes, target, positions=11):
    tgt = bytes.fromhex(target)
    for s in shapes:                                    # A
        blob, syms = _compile(s)
        if blob and _slice(blob, syms, "T") == tgt:
            return "A", "isolated"
    for si, s in enumerate(shapes):                     # B
        for ti, ps in enumerate(PADSETS):
            parts = []
            for c in range(positions):
                pads = "\n".join(ps[k % len(ps)].format(n=f"{si}_{ti}_{c}_{k}")
                                 for k in range(c))
                inst = s.replace("int T(", f"int T{si}_{ti}_{c}(", 1)\
                        .replace("void T(", f"void T{si}_{ti}_{c}(", 1)
                parts.append(pads + "\n" + inst)
            blob, syms = _compile("\n".join(parts))
            if blob is None:
                continue
            for c in range(positions):
                if _slice(blob, syms, f"T{si}_{ti}_{c}") == tgt:
                    return "B", f"shape{si} padset{ti} pos{c}"
    blob, syms = _compile(shapes[0])                    # C validity gate
    b = _slice(blob, syms, "T") if blob else b""
    if b is None or _itypes(b.hex()) != _itypes(target) or len(b) != len(tgt):
        return "C?", "reconstruction incomplete (not a valid version-block)"
    return "C", "no context in battery"


def main():
    default = os.path.join(REPO, "config/targets/1ST_READ.abc_sample.json")
    path = sys.argv[1] if len(sys.argv) > 1 else default
    cases = json.load(open(path))
    from collections import Counter
    res = {}
    for name, (tgt, shapes) in cases.items():
        cls, detail = classify(shapes, tgt)
        res[name] = cls
        print(f"{name:26} -> {cls:3} ({detail})")
    print("counts:", dict(Counter(res.values())))


if __name__ == "__main__":
    main()
