# docs/FINDINGS/ — residual-diff analyses (failure protocol)

Per CLAUDE.md: a persistent non-match after honest iteration is documented
here, one file per function (`<target>_<vma>.md`), with the residual diff
*described in prose* — instruction counts, idiom classification, hypotheses —
never as byte dumps or disassembly listings of game code.

A function documented here keeps `status: attempted` in its manifest record
and its bytes stay spliced from the locally-extracted original by the
placeholder mechanism until it matches.
