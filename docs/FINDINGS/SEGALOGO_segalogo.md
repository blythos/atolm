# Residual-diff analysis: SEGALOGO.PRG unit `segalogo` (0x06054000, 0x148 bytes)

**Status: `attempted` — persistent 11-byte non-match after honest iteration
(≈50 source-shape variants + full flag sweep), 2026-07-17.**
Best candidate: `src/SEGALOGO/SEGALOGO.c`, 317/328 bytes identical (96.6%).
Built with shc-5.0-r31, `-optimize=1 -speed`.

## What matches

Everything structural: both function sizes and boundaries, every opcode and
operand except the clusters below, all field offsets and addressing-mode
choices (r0-indexed stores for large offsets, the explicit add-then-store
idiom through the reloaded display-list pointer, displacement stores for
small offsets), branch types and displacements (including the forward `bsr`
to the static init function and the entire tail-call `jmp` sequence with
the frame restore in its delay slot), callee-saved register assignment
(r14/r13/r12), literal-pool contents, the word/long pool split, and pool
ordering — except where noted.

## The three residual clusters (11 bytes)

1. **Entry epilogue schedule (8 bytes, unit offsets 0x28–0x33).** The same
   five instructions in both: restore pr, move the call result into r5,
   load the tail-call target from the pool into r3, set arg registers.
   The original restores pr immediately after the call returns and emits
   the first argument before the others; Release31 hoists the pool load
   above the pr restore and emits arguments in the opposite order. Same
   instructions, permuted.
2. **Constant-derivation peephole (2 bytes, offset 0xaa).** For the third
   short store the original derives the offset 0xfc by `add #2` from the
   0xfa still live in r0; Release31 loads 0xfc from the literal pool
   instead. Suppressing/triggering this peephole proved sensitive to
   compiler-internal table state (adding or removing an unrelated local
   variable toggles it) but no source shape produced it together with the
   otherwise-correct code.
3. **Pool padding word (1 byte, offset 0xe2).** Consequence of cluster 2:
   the original pads the odd word-pool slot with zero; Release31 stores
   the 0xfc constant there.

## Why this is classified version-drift

- All three clusters are scheduling/peephole choices with zero semantic or
  structural difference — the same class as Bucket 0.5 candidate 3
  (temp-register numbering) and candidate 4 (constant materialization).
- A 10-set flag sweep on the final source (`-optimize=1` alone, `-nospeed`,
  `-size`, `-noinline`, `-cpu=sh1`, `-macsave=0/1`, `-rtnext`, `-align16`,
  `-abs16=all`) left the residual byte-for-byte unchanged (except
  `-align16`, which only adds padding) — reconfirming Bucket 0.6's finding
  that these choices are hard-coded in this build.
- Source-shape iteration covered: pointer variables vs constant derefs vs
  cast arithmetic (each produces distinct codegen; the match required a
  specific mix), `register` on every subset of locals, declaration and
  assignment order permutations, chained vs separate assignments, nested
  vs temped call arguments, explicit `return`, implicit-int, typed temp
  variants (int/long/unsigned), function-pointer locals, value-temp
  variables, and unused entry parameters. The 11 bytes were invariant
  under all of them once the rest matched.

Standing watch applies: if an SHC 2.x–4.x binary surfaces, re-run this
unit against it first — the residual pattern (epilogue scheduling + a
missing peephole) is exactly what a one-generation-older code generator
would plausibly resolve.

## Reproduction

`tools/check_units.py` recompiles the unit; the manifest keeps
`status: attempted` so the build splices the original bytes (placeholder
mechanism) and `make check` stays green pending a true match.
