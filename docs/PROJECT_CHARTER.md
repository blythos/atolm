# atolm — Panzer Dragoon Saga Matching Decompilation
## Project Charter & Anti-Drift Record

**Last updated:** 2026-07-18 (Bucket 2 closed)
**Purpose of this document:** the canonical statement of what this project is, every binding decision made so far, and the guards against goal drift. A previous attempt at this project failed through gradual drift; this document exists so that any future conversation, agent session, or contributor can be checked against it. **If work diverges from this document, the work is wrong, not the document — unless a human explicitly amends the document.**

**Canonical copy & sync rule (amended 2026-07-18):** the canonical charter is docs/PROJECT_CHARTER.md in the atolm repo; git history is the amendment ledger. The claude.ai project-knowledge copy is a mirror, refreshed by the human at bucket closes. Amendments are applied only as verbatim blocks approved at a checkpoint review — the agent never amends charter content on its own judgment. If copies differ, the repo copy wins.

---

## 1. Goal statement (verify all work against this)

Produce a **verified, byte-matching decompilation** of Panzer Dragoon Saga (Sega Saturn, Team Andromeda, 1998; US release, product MK-81307, 4 discs) — a public source tree where correctness means *compiles to bytes identical to the original binaries*.

- **The only progress metric the project recognizes is matched code.**
- A function is *matched* when its recompiled bytes are identical to the original, proven by cmp/sha256 output. "Behaves the same," "looks equivalent," or "close" is **not** a match.
- The modern reimplementation (playable port) is **explicitly deferred** until the decompilation is mature. It is a separate future phase (referred to as "B"), consuming the verified decomp — never the method of verifying it.

### Origin of this framing (the interview, July 2026)
- "Worth having done" = the decompilation itself, with verification people can trust.
- Deliverable choice: **A (matching decomp — the verified source tree is the artifact)**, not B (extraction/translation tooling). Decision: *"I would do A if it is possible, then do B at a later time."*
- Key insight that resolved A-vs-B confusion: **A is self-verifying** — the byte-match is the proof; no runtime, viewer, or gameplay test is needed or accepted as verification.
- Audience: **primarily Stephen's project, with community legibility.** Public on GitHub; contribution infrastructure is not an early requirement.

## 2. Why the previous attempt failed (the drift this document guards against)

The original atolm repo (now renamed **pds-asset-tools**) stated "full decompilation and modern reimplementation" as its goal but became entirely an **asset extraction pipeline** (model extractors, FMV converters, MIDI tools, viewers). Assets give visible wins; decompilation gives none for months. That gravity well is the named enemy.

**Standing drift guards (binding):**
1. Matched bytes are the sole progress metric.
2. **Asset work is banned in the decomp repo** — it belongs to the sibling repo pds-asset-tools.
3. Every bucket ends with a checkpoint where work is re-read against this goal statement.
4. Assumptions are flagged explicitly and listed, never silently absorbed.
5. Success criteria are never quietly satisfied on technicalities (see the "ascending pocket" episode, §5).
6. "Make X generic" tasks are out of scope (deferred to the Saturn Decomp Kit, §9); only "match X" tasks are in scope.
7. No new infrastructure before the need is demonstrated (Ghidra, permuter etc. enter at defined triggers, not by default).
8. **Layer-3 sync (added 2026-07-17):** the environment artifacts that enforce these rules (CLAUDE.md files, settings.json deny rules, gitignore/tripwire) are re-checked against this charter at every checkpoint; any charter amendment propagates to them in the same checkpoint commit. Prose here that isn't enforced there is a bug in the environment, not a substitute for it.

## 3. Methodology (how work is conducted)

Three-layer discipline used throughout:
- **Layer 1 — Spec:** interview before work; smallest independently reviewable buckets; hard checkpoints (STOP = present results, end turn, human reviews before continuation); assumptions flagged and listed.
- **Layer 2 — Verifier:** exact, checkable success criteria stated before work; every completion claim accompanied by re-runnable verification output (cmp/sha256/objdump), never bare assertion; outputs reviewed by a second model (the claude.ai project conversation) at every STOP.
- **Layer 3 — Environment:** durable rules live in CLAUDE.md files (per repo), not per-message prompts; protected paths enforced by settings.json deny rules AND filesystem permissions, not prose; scope bans written into the environment.

**Bucket protocol:** work proceeds in small buckets, one at a time; each bucket has explicit success criteria, non-goals, a failure protocol, and a checkpoint. Scope extensions to closed buckets get named (0.5, 0.6, 0.6b), never slid into.

**Failure protocol pattern:** persistent non-match after honest bounded effort → STOP and write failure analysis; never relax the match criterion. The fallback decision always belongs to the human.
- **Interim per-function effort bound (added 2026-07-17; human-adjustable default, pending Bucket 3's formal per-function loop):** roughly **5 source-shape attempts or one focused hour**, whichever comes first — calibrated to Bucket 0.5's observed 2–5-attempt resolution range. On hitting the bound: STOP, write the failure analysis (which idiom family the residual falls into), leave the segment as `code_unmatched`, move on. Some fraction of functions is expected to be unmatchable until an era-correct compiler surfaces (§4); grinding past the bound on those is waste, not rigor.

**Task routing (two-agent rule):** Claude Code in WSL for anything touching the match/verify loop (src/, config/, toolchain/, builds, any claim of "matches"). Antigravity on Windows only for work it can verify where it stands (docs drafting, Windows-runnable Python). *An agent may only do work it can verify where it stands.*

**Environment:** WSL2 Ubuntu (host: Windows 11), Docker (systemd enabled in WSL), work on the Linux filesystem (~/atolm, ~/pdstest), never /mnt/c. Canonical verification environment = the Docker containers = what CI runs.

## 4. Confirmed findings (Buckets 0, 0.5, 0.6, 0.6b — July 2026)

**Reference disc:** US release, MK-81307, release date 19980318 (from IP.BIN). **1ST_READ.PRG (253,650 bytes) loads at 0x06006000** (per IP.BIN header offset 0xE8 — NOT the conventional 0x06004000; always trust the disc's own header over community-quoted values). Other extracted targets: SEGALOGO.PRG (3,620), CHANGE.PRG (3,644), TITLE.PRG (1,807).

**Compiler identification (the headline finding, believed novel):**
- PDS's dominant code population was compiled with **Hitachi SHC** — established by prologue-idiom fingerprinting: 351 of 354 multi-register prologues in 1ST_READ.PRG push callee-saved registers in **descending** order (r14→r8, `sts.l pr,@-r15` last, ascending pop), matching real SHC output and the exact opposite of Cygnus GCC's ascending convention. Register-save order proved a cheap, fully diagnostic compiler fingerprint (caveat: silent on functions too small to save registers).
- Verified with resurrected period compilers, not inference: Cygnus GCC 2.7-96Q3 (DOS, via dosemu2 in Docker — sotn-decomp's recipe) and Hitachi SHC 5.0 Release31 (Win32, via Wine in Docker). Version-timeline calibration point: Katana R9 (Dreamcast, Nov-1999) ships SHC 5.1 Release04 — acquired, hashed, calibration-only.
- **Canonical toolchain: SHC 5.0 (Release31), flags `-optimize=1 -speed`** — corroborated by CRI's own sample build files using -OP=1 -SP (same flags, older spelling). Canonical invocation, environment, and reproduction transcript: `work/MATCHED_FUNCTION/INVOCATION.md`.
- **Standing caveat — upgraded to demonstrated fact (0.6b, 2026-07-17):** Release31 is provably a Nov-1998 Dreamcast-devkit redistribution, and **codegen drift versus PDS's compiler is now proven by controlled experiment**: the Sept-1997 SDTK disc (Exodus mirror, L21-1000) ships SBL 6.21/SGL 3.20 libraries with translator tags C_SH9705xx–9708xx (built May–Aug 1997, flags -optimize=1 -cpu=sh2) plus a source file (DMA_CPU0.C) with its exact build recipe; recompiling that source under Release31 with source+flags held constant yields a different-sized P section (380 vs 392 bytes) with pervasive instruction-selection differences of exactly the near-miss family. Three independent discriminators (single-use offset addressing 976:73 in PDS matching 1997-style; the mask-test idiom 18:4 in PDS vs Release31's inverted 2:11 on the recompile; the head-to-head) all side PDS with 1997-SHC. Idiom detectors were validated byte-exact against the Bucket 0.5 matched function before use. (A 1994 O0-compiled sample on the same disc gave no signal — the discriminating idioms don't occur at -optimize=0; reported for completeness.) **The version hunt narrows to a mid/late-1997 SHC build** (likely 4.x/early pre-R31 5.0 — earlier 2.x may not even be necessary); drift occurred between then and Nov-1998. No surviving binary found in: archive.org SDKs, antime.kapsi.fi, Hidden Palace, SegaXtreme, Psy-Q archives, Exodus techdocs/DTS mirror (SBL601.ZIP dead link; L21-1000 SDTK fully inventoried incl. HFS partition — GNU compilers only; Sega discs instruct SET SHC_LIB for a *separately installed* compiler, confirming SHC never shipped via Sega). **Standing watch item:** if a mid-1997-era SHC surfaces, re-run the four-candidate battery (~30 min); banner-independent dating test: compile a scrap and read the translator tag its object carries (want C_SH97xxxx).
- Why SHC is scarce: **Sega never distributed SHC** — every Sega dev disc 1995–97 bundles Cygnus + Psy-Q only; SHC was a separate commercial Hitachi product.
- SN Systems' Psy-Q "ccsh" = rebadged Cygnus GCC 2.7-97r1a (ascending idiom, GCC-family, disqualified for the main population; second candidate for the pocket).

**Match evidence:**
- **First byte-identical match:** 18-byte, 9-instruction leaf function at **0x06006622** in 1ST_READ.PRG (pure register arithmetic, zero callee-saved registers — chosen to sidestep the idiom risk areas by construction), sha256-equal, zero-diff, matched first attempt (Bucket 0 Step 5c). Proof artifacts in `work/MATCHED_FUNCTION/`.
- **Validation set (Bucket 0.5):** four graduated candidates; 1 exact match, 3 near-misses with *consistent, narrow* gaps — candidate 2 (0x0600ada4): indexed-addressing vs explicit-pointer choice; candidate 3 (0x060067f8 + callee): temp-register numbering only, call machinery exact; candidate 4 (0x0603a9f4, 80 bytes): immediate-chaining vs literal-pool constant materialization. Option-space sweep (22 flag sets × 3 candidates = 66 runs, from shc.exe's own 36-option list, sha256-verified) **falsified** the "wrong flags" hypothesis — the gaps are hard-coded behavior of Release31 (21 of 22 optimized flag sets produced bit-identical output to each other for candidates 2–3). Classification: version-drift now proven (see 0.6b above); **operative path = source-shape iteration with Release31** (normal decomp grind, bounded per-function per §3), with the honest expectation that most real functions need iteration and some fraction stays unmatchable until the 1997 compiler surfaces.
- Flags hold globally (no per-function flag hunting; confirmed across 9–80 instructions, 0–1 calls, 0–17 branches). SHC's assembler resolves near calls to direct `bsr` with correct displacement from same-file compilation order (no Cygnus-style -mrelax complications; confirmed on adjacent functions, worth re-confirming at longer ranges before relying on it broadly).
- **Operational gotchas are required reading before match work** and live in FINDINGS.md §Gotchas — headline items: SHC env vars need trailing backslashes (error 3321 otherwise); elfcnv mislabels ELF endianness (cosmetic; use `sh-elf-objdump -EB`) and fails on unresolved externals; SHC's inliner is aggressive at `-optimize=1 -speed` (per-function inline/noinline determination needed); function-boundary detection must use prologue starts, not "previous rts" (multiple-return functions mis-split otherwise); objdump decodes trailing literal pools as fake instructions — visually inspect boundaries.

**Two-population structure:** an isolated 3-function **ascending-order pocket** at 0x06022820–0x0602297c (GCC-idiom) sits inside the otherwise-SHC binary. Hypothesis (unconfirmed): statically linked third-party middleware, candidate CRI (a "CPK Version 1.24 1996-06-14" string exists in the binary). Candidate compilers for the pocket: Cygnus 2.7-96Q3 or ccsh 2.7-97r1a. A timeboxed Bucket 0 attempt got structurally close (correct offsets, constants, loop idiom) but not byte-identical; any future attempt needs full-context linking with `-mrelax`/`-relax` (documented in the Cygnus distribution's RELAX.TXT). **Matching the pocket does NOT count toward main-population success criteria** (amended criterion, 2026-07-15 — the on-record example of refusing a technicality win).

**Other structural knowledge:** PDS is heavily overlay-based (hundreds of .PRG files streamed from disc; the 973-filename runtime file table observed in savestate RAM is built at runtime — it is NOT present in 1ST_READ.PRG; only small filename tables live there). Much game logic lives in a script/bytecode VM — script programs are *data* to the decomp, shrinking the true code-matching surface. Sega SGL/SBL 1996-era libraries are linked in (version strings: BUP 1.21, GFS_SBL 2.10, SYS 2.20, CPK 1.24). Period SBL 6.21/SGL 3.20 library binaries (26 .LIBs + SYS_*.OBJs, translator-tagged, sha256-catalogued in `work/0.6b/lib_catalogue.md` in ~/pdstest) are in hand as ready-made fingerprints for Bucket 3 library identification.

## 5. Instructive episodes (precedents to reason from)

- **The ascending-pocket temptation:** Bucket 0's success criterion ("one matched function") could have been literally satisfied by matching the 3-function middleware pocket with the already-working Cygnus toolchain — technically compliant, meaningless for feasibility. The criterion was **amended on the record** to require the dominant population. *Precedent: criteria get amended explicitly when reality shifts; they never get satisfied on technicalities.*
- **The ccsh scope-override:** the agent flagged Psy-Q's ccsh as "out of scope" (not a Hitachi dot-release); the human review overrode: the hypothesis was always "a different compiler whose defaults produce the observed codegen," vendor included. *Precedent: scope serves the question, not the letter.*
- **H1 falsification accepted cleanly:** a 66-run option matrix produced zero matches and was recorded as a real negative result, per option set. *Precedent: negative results are findings, logged with the same rigor.*
- **Model-swap incident:** a session silently reverted to a smaller model; the work held because verification is structural (hashes, re-runnable commands), not trust-based. *Precedent: the discipline, not the model, carries correctness.*
- **The fabricated-hash incident (Bucket 2):** an agent hand-typed plausible sha256 tails into a manifest instead of computing them; the verification loop caught it, all hashes were regenerated from real bytes, and the incident was self-reported. Standing rule: proof values (hashes, sizes, addresses) are only ever tool-generated — a hand-authored proof value is treated as fabrication regardless of intent, and manifest edits must come from the generating tools.

## 6. Repositories, artifacts & legal rules

- **github.com/blythos/atolm** — the decomp (fresh repo; old repo renamed to pds-asset-tools, redirect knowingly severed).
- **github.com/blythos/pds-asset-tools** — the former atolm; asset pipeline lives there; useful prior work: iso9660.py (vendored into decomp repo), format knowledge, PRG-bytecode findings.

**Repo mechanics (decided at Bucket 1 Checkpoint 1, 2026-07-16):** each PRG target carries a **manifest** recording (a) extraction identity (source file hashes), (b) an ordered segment map, and (c) per-function records keyed to compiler+flags with original-byte hashes. Unmatched code is an explicit segment class (`code_unmatched`), spliced at build time from local gitignored `extracted/` — the placeholder mechanism is data, not build-logic magic. The manifest is the load-bearing artifact that makes CI verifiable with zero disc content; changes to its format are checkpoint-level decisions. Build system: plain Make + small Python (deliberately no ninja/etc. at current scale, per drift guard 7).

**Legal rules (absolute):**
- **Zero Sega-derived bytes in the repo:** no disc images, extracted PRGs, disassembly listings, data segments, or hex dumps of game code. Enforced by gitignore + CI tripwire.
- Users supply their own disc; extraction is local-only into gitignored paths.
- **SHC is Hitachi's proprietary binary — never committed;** fetched by pinned-sha256 script into gitignored vendor/ (single-point-of-failure noted; "bring your own archive" fallback to be documented).
- CI model (decided): **strict hash-based** — CI verifies committed C compiles and per-function output hashes match recorded values + tripwire; full-PRG byte verification is local-only (make check) where the disc lives.
- Public writeups describe findings without reproducing Sega bytes.
- Attribution discipline: docs/ATTRIBUTION_AND_FINDINGS.md tags every claim [ORIGINAL] / [PRIOR ART] / [COMMUNITY RESOURCE], with a standing corrections-welcome posture. Key prior art: the matching-decomp methodology (sm64/OoT lineage), sotn-decomp's Saturn recipe (xeeynamo), sozud's saturn-compilers/splitter, yaz0r's Azel (MIT; reference/Rosetta stone for identification and naming — **its code is behavioral reimplementation, never importable as "matched"**).

## 7. Bucket ledger

**Closed:**
- **Bucket 0 — GO/NO-GO:** GO. Compiler identified, toolchains resurrected, first byte-identical match. (Amended criterion: match must come from the dominant population.)
- **Bucket 0.5 — validation set:** 4 graduated candidates; calibrated difficulty (most functions need iteration; obstacles mechanical and bounded).
- **Bucket 0.6 — near-miss resolution:** flags falsified as cause; Release31 canonical with standing watch.
- **Bucket 0.6b — watch-item follow-up (Exodus techdocs):** no compiler found, but version-drift **proven** by controlled recompile of disc-shipped source, and the hunt narrowed to mid/late-1997 SHC (translator tags C_SH9705xx–9708xx). Side prize: SBL 6.21/SGL 3.20 period libraries acquired, hashed, and catalogued (work/0.6b/lib_catalogue.md in pdstest) — ready-made fingerprints for Bucket 3 library identification. Remaining hunt channels: Hitachi/embedded-world archives and community outreach (personal, ongoing), not Sega-preservation channels (falsified twice).
- **Bucket 2 — analysis infrastructure:** CLOSED (2026-07-18). 1ST_READ fully segmented (3,626 functions, evidence-tagged, 84.9% instruction-covered, 4.1% unclassified; 555 suspects triaged to Bucket 3); reproducible headless Ghidra generation (tools-local, never committed); five-state vocabulary live and machine-enforced; symbols file with provenance tags (21 entries); Azel pilot stopped at 19 names but established JP/US address identity (19/20 exact) — structural matching against yaz0r's ~700 named functions logged as a Bucket 3+ lead; Ymir savestate fixture confirmed load address 0x06006000 and a 440-byte runtime-write mask; overlay locate technique established for Bucket 4.

**Active:**
- **Bucket 1 — repo + first complete PRG target (SEGALOGO.PRG, 3620 bytes):** Step 1 (migration/skeleton/build design) checkpoint PASSED and committed; Step 2 (extract + segment) approved and in progress. Remaining: extract+segment → build system (make / make check, placeholder splicing from extracted/) → match functions → CI (hash-verify + tripwire) → README → final checkpoint (clean clone → setup → extract → build → check green, byte-identical). Non-goals: no second PRG, no 1ST_READ beyond existing proofs, no Ghidra/permuter, no assets, no progress website. **Ghidra trigger:** if SEGALOGO segmentation proves ambiguous, Ghidra moves up immediately.

**Planned (order subject to checkpoint review):**
- **Bucket 2 — analysis infrastructure:** Ghidra (SH-2, correct load addresses; savestates as fixtures), code-vs-data segmentation at scale, symbol conventions, Azel-derived naming hypotheses (marked unverified).
- **Bucket 3 — workflow at function scale:** SGL/SBL library identification/matching using the catalogued 0.6b libraries (one-time, benefits every overlay; fingerprint via module boundaries + P-section bytes with reloc holes wildcarded), asm-differ/objdiff, decomp-permuter plumbing for SHC, per-function loop documentation (supersedes the interim effort bound in §3).
- **Bucket 4 — scale-out:** overlay-by-overlay; overlay similarity clustering (dedup — expected large win given PDS's templated overlays); progress tracking (simple JSON + badge first).

**Deferred ledger (explicit triggers, not dates):**
- **Bucket N — public methodology writeup** (compiler fingerprinting, toolchain resurrection, "wanted: mid-1997 SHC" appeal). Seed: the attribution doc.
- **Saturn Decomp Kit** (second project generalizing the tooling). Trigger: **first complete overlay matched.** Until then: keep docs game-agnostic where free; no abstraction work.
- **Pocket/CPK confirmation** (nice-to-have; full-context + relax linking per §4).
- **Reimplementation (B)** — far horizon, explicit re-decision required.
- **Savestate emulator identification** — open assumption; matters when Bucket 2 needs load-address fixtures. (Savestates = analysis fixtures only; never part of verification.)

## 8. Working agreements with the assistant (claude.ai side)

- Interview before plans; one question at a time when interviewing.
- Present plan → checkpoint → human review → proceed. Never proceed past a STOP.
- Flag assumptions explicitly, separately, before proceeding.
- Verify key decisions against the goal statement at every checkpoint; name any divergence.
- **Checkpoint ritual also includes (added 2026-07-17):** confirming CLAUDE.md/settings.json still encode current charter rules (drift guard 8), and refreshing the repo's charter mirror if this document was amended.
- Review agent outputs (the "second model" role) — including overriding agent judgment where it conflicts with intent (see ccsh episode).
- Explanations on request at any technical level (including plain-English and creative registers for sharing with friends).
- Commit-at-checkpoint rhythm: every passed checkpoint gets a commit; git history = checkpoint ledger. Publishing (push) is a human act (agent push denied by settings).

## 9. Document map (where knowledge lives)

The charter is the anti-drift spine, not the encyclopedia. Detailed evidence lives in these canonical artifacts; a fresh session should know they exist and consult rather than re-derive:

| Artifact | Location | Contents |
|---|---|---|
| This charter | claude.ai project knowledge (canonical); `docs/PROJECT_CHARTER.md` (mirror) | Goal, guards, decisions, ledger |
| FINDINGS.md | ~/atolm work tree (and project knowledge) | Full Bucket 0/0.5/0.6 evidence: fingerprinting, toolchain stand-up, all four candidates with C source, the 66-run sweep, acquisition tables, **the gotcha list** |
| FINDINGS_0_6b.md | ~/pdstest (and project knowledge) | SDTK inventory, drift proof, idiom censuses, library catalogue summary |
| INVOCATION.md | ~/atolm `work/MATCHED_FUNCTION/` | Canonical compiler invocation, environment, verification transcript |
| lib_catalogue.md | ~/pdstest `work/0.6b/` | sha256 manifest of period SBL/SGL libraries for Bucket 3 |
| CLAUDE.md + settings.json | each repo | Agent rules, protected paths, scope bans (Layer 3 enforcement) |
| ATTRIBUTION_AND_FINDINGS.md | `docs/` in atolm | Claim provenance tags |
| Per-PRG manifests | atolm repo | Segment maps + per-function hash records (§6) |

## 10. Quick orientation for a fresh session

Read §1 (goal), §2 (drift guards), §7 (where we are), §9 (what exists — don't re-derive). The active question is always: *does this work produce or protect matched bytes?* If not, it belongs elsewhere (asset repo, deferred ledger) or nowhere. When in doubt: smaller bucket, explicit criteria, checkpoint, verify with output, commit.

**Known error in auto-generated conversation summaries:** at least one past-conversation summary states 1ST_READ.PRG "loads at 0x06006622." That conflates two facts. Correct values: **load address 0x06006000** (IP.BIN header); **0x06006622 is the first matched function**. Conversation summaries are lossy; where they conflict with this charter or the FINDINGS files, those win.
