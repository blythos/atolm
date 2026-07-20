# 1ST_READ.PRG — SHC codegen is translation-unit-context-dependent

**Date:** 2026-07-20 (Bucket 4 STOP 2)
**Status:** decision-grade; reshapes the matching model and the permuter design.

## The discovery

While building the scoped permuter (STOP 2), the reconstruction of the
0x06026f3c cluster produced a result that only makes sense one way:
**SHC Release31 compiles the *same* function source to *different* (but
deterministic) machine code depending on the functions that precede it in the
translation unit.**

Minimal proof — three textually identical functions in one file:

```c
void a(p) long *p; { int n=32; do { p[1]=(long)p; p+=2; } while(--n); }
void b(p) long *p; { int n=32; do { p[1]=(long)p; p+=2; } while(--n); }
void c(p) long *p; { int n=32; do { p[1]=(long)p; p+=2; } while(--n); }
```

compile (canonical flags) to:

- `a` (position 1): `dt` scheduled before the store;
- `b` (position 2): **store before `dt`** — byte-identical to the shipped
  0x06030f42;
- `c` (position 3): `dt`-first again.

Same tokens, three schedules. The effect is deterministic (reproducible, a
position-parity pattern), not nondeterminism. Register allocation shows the
same context-sensitivity: a one-character source change (`sum += t*w` vs
`sum = sum + t*w`) moved `sum` from r1 to r6, and prepending different
functions moved it again.

## Why it matters — the STOP-1 "drift" picture was incomplete

STOP 1 classified the cluster's residuals as families #3 (schedule) and #4
(register-numbering) and, after 570+ source variants failed to close `cksum`,
leaned toward "source-invariant R31 behaviour → needs the 1997 compiler." That
was half right. The residuals ARE #3/#4 — but a large part of #3/#4 is **not
source-invariant; it is translation-unit-context-invariant.** The same R31 can
emit the target schedule — just not for the function compiled first or in
isolation. The 570-variant sweep held context fixed (each candidate first/alone)
and so could never see it.

Concretely, on the proof-of-machine cluster (0x06026f3c, matched in binary
order A,B,C):
- `store_cksum` (B) matched — its codegen has no scheduling freedom at its
  position, so it is position-robust.
- `cksum` (A) and `verify_cksum` (C) did not — both have delay-slot / reorder
  freedom, and at their positions in a *minimal* 3-function reconstruction the
  scheduler state differs from the real module, where `cksum` is preceded by
  many functions (it is called from six sites spanning ~1.3 KB).

## Refined model

A function's shipped bytes are fixed by **three** reconstruction requirements,
not two:
1. **spatial — bsr displacement** (co-compile caller+callee): STOP 1.
2. **spatial — literal-pool placement** (shared-pool cluster): Bucket 3.
3. **NEW — scheduler/allocator context**: the functions that precede it in the
   translation unit, in order. This is why the analysis-level TU (the undirected
   `bsr`+pool closure — for a shared leaf, the whole ~18 KB module) is the true
   compilation unit, while the *minimal reproducing unit* (tools/tu_cluster.py
   `minimal_unit`) is necessary but **not always sufficient** for byte-fidelity.

## What is and isn't reachable (measured)

Tiering test (cheap-tier permuter, tools/permute.py) + cluster:

| target | outcome | note |
|---|---|---|
| 0x06007788 (leaf, 3 stores) | **MATCHED** (try_match-proven) | position-robust |
| 0x06026f58 `store_cksum` | **MATCHED** (in-unit, STOP 1) | position-robust at pos 2 |
| 0x06030f42 (leaf, loop) | reachable at **position 2**, not 0 | position-dependent #3 |
| 0x06007796 (leaf, 3 stores + const) | near (2-instr const-load timing) | position-dependent #3 |
| 0x06026f3c `cksum` | not closed (570 src × 12 context) | needs specific real context |
| 0x06026f6e `verify_cksum` | not closed (bsr delay-slot fill) | position-dependent #3 |

So some residuals close with the right context (0x06030f42), and some need
context we have not yet reconstructed (`cksum`). None yet require the 1997
compiler on this evidence — the pessimistic STOP-1 read is softened: a chunk of
#3/#4 is R31-reachable via context, not a version wall.

## Consequences for the permuter decision (STOP 3 input)

- **A pure-source permuter is insufficient.** The search space must include
  **translation-unit context** — position, and the identity/order of preceding
  functions. `decomp-permuter` mutates source within one function; it does not
  model "what precedes me." Adopting it unmodified would miss this axis.
- **A context/position permuter is a new, cheap lever** worth building: for a
  target with scheduling freedom, search over preceding-function padding /
  ordering until the scheduler state matches. 0x06030f42 shows it works.
- **The matching unit for byte-fidelity trends toward the whole ordered TU.**
  Scale-out must reconstruct translation units in order, not just bsr/pool
  clusters. This raises the per-unit cost and is the central planning input for
  the rest of Bucket 4.

## Reproduce

```
# position-dependence (three identical functions -> three schedules):
printf 'void a(p)long*p;{int n=32;do{p[1]=(long)p;p+=2;}while(--n);}\n%s\n%s\n' \
  'void b(p)long*p;{int n=32;do{p[1]=(long)p;p+=2;}while(--n);}' \
  'void c(p)long*p;{int n=32;do{p[1]=(long)p;p+=2;}while(--n);}' > /tmp/t.c
tools/try_match.sh ... # or compile via toolchain/shc/run.sh and read .bin
```
`tools/tu_build.py <seed>` reports per-member verdicts on a reconstructed unit;
`tools/permute.py` searches source (and, via batch position, context).
