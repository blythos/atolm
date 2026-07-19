#!/usr/bin/env python3
"""Azel structural-name propagation pilot (Bucket 3 deliverable 4, BOUNDED).

Anchors: the hypothesis-azel + library-identified symbols (known US
address <-> name). Signal: a US function's *anchored-callee signature* — the
set of anchored functions it calls (from tools/callgraph.py) — matched against
the set of the same names each Azel C++ function calls. A US function whose
signature equals exactly one Azel function's called-anchor set is a name
hypothesis. Confidence tiers by signature size (bigger = more distinctive).

Names-only, never code, never "matched" (charter §6). Output: proposed
hypothesis-azel rows for review; the pilot reports yield and stops.
"""
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prg import REPO

AZEL = os.path.join(REPO, "reference/Azel")
FUNC_DEF = re.compile(
    r"(?:^|\n)[A-Za-z_][\w:<>,\* &]*?\b([A-Za-z_]\w+)\s*\([^;{}]*\)\s*\{")


def azel_call_sets(anchor_names):
    """For each Azel function body, the subset of anchor_names it calls."""
    names = set(anchor_names)
    tok = re.compile(r"\b([A-Za-z_]\w+)\s*\(")
    fn_calls = defaultdict(set)   # azel function name -> anchor names it calls
    for root, _dirs, files in os.walk(AZEL):
        if "/build" in root or "/ThirdParty" in root:
            continue
        for fn in files:
            if not fn.endswith((".cpp", ".c")):
                continue
            text = open(os.path.join(root, fn), encoding="utf-8",
                        errors="ignore").read()
            # split into function bodies by brace matching from each def
            for m in FUNC_DEF.finditer(text):
                fname = m.group(1)
                i = text.index("{", m.end() - 1)
                depth, j = 0, i
                while j < len(text):
                    if text[j] == "{":
                        depth += 1
                    elif text[j] == "}":
                        depth -= 1
                        if depth == 0:
                            break
                    j += 1
                body = text[i:j]
                called = {t for t in tok.findall(body) if t in names}
                called.discard(fname)
                if called:
                    fn_calls[fname] |= called
    return fn_calls


def main():
    cg = json.load(open(os.path.join(REPO,
                  "build/analysis/1ST_READ.callgraph.json")))
    cg = {int(k, 16): [int(x, 16) for x in v] for k, v in cg.items()}
    anchors = {}
    for line in open(os.path.join(REPO, "config/symbols/1ST_READ.PRG.sym")):
        line = line.split("#")[0].strip()
        p = line.split()
        if len(p) >= 3 and p[0].startswith("0x"):
            anchors[int(p[0], 16)] = (p[1], p[2])
    name_of = {a: n for a, (n, _) in anchors.items()}
    existing = set(anchors)

    # US anchored-callee signatures (only functions that are not themselves
    # already named, and not the anchors)
    us_sig = {}
    for caller, callees in cg.items():
        sig = frozenset(name_of[c] for c in callees if c in name_of)
        if sig and caller not in existing:
            us_sig[caller] = sig

    fn_calls = azel_call_sets(set(name_of.values()))
    # invert: signature -> azel function names that produce it
    sig_to_azel = defaultdict(set)
    for azf, called in fn_calls.items():
        sig_to_azel[frozenset(called)].add(azf)

    proposals = []
    for addr, sig in us_sig.items():
        cands = sig_to_azel.get(sig, set())
        if len(cands) == 1:
            proposals.append((addr, next(iter(cands)), sig))

    proposals.sort(key=lambda p: (-len(p[2]), p[0]))
    print(f"# Azel propagation pilot: {len(us_sig)} US functions with an "
          f"anchored-callee signature; {len(sig_to_azel)} distinct Azel "
          f"signatures.")
    print(f"# {len(proposals)} unique-signature name hypotheses:")
    print("# addr\tproposed_name\tconfidence\tsignature")
    for addr, name, sig in proposals:
        conf = {1: "low", 2: "med"}.get(len(sig), "high")
        print(f"0x{addr:07x}\t{name}\t{conf}({len(sig)})\t{'+'.join(sorted(sig))}")


if __name__ == "__main__":
    main()
