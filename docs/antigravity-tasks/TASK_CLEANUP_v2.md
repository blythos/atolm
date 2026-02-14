# Task: Repository Cleanup

## Context

This is part of the Panzer Dragoon Saga decompilation project. Repository: https://github.com/blythos/atolm

Read `.antigravity/rules.md` and `docs/PROJECT_INSTRUCTIONS.md` before starting.

## Problem

The `tools/` directory has accumulated broken/abandoned scripts from previous failed implementation attempts. These need to be cleaned up before we add new tools.

## What to Delete

Delete these files/directories from `tools/` if they exist. They are debugging artifacts or failed implementations that have been superseded:

1. **Any model viewer or 3D viewer code** — The browser-based model viewer was attempted but failed. All of this code should be removed. This includes any HTML, JS, Python HTTP server scripts, Three.js integration code, or related files that were part of the viewer attempt. Look for files/directories with names containing: `viewer`, `model_viewer`, `browser`, `server`, `three`, `3d_viewer`, or similar.

2. **Any MCB/CGB parsing scripts that are NOT `mcb_extract.py`** — There may be abandoned parsing attempts. The canonical extractor is `mcb_extract.py` (being added separately). Remove any other `.py` files that attempt MCB parsing, model extraction, or glTF generation, UNLESS they are clearly a different tool (like `cpk_extract.py` for video).

3. **Any `test_*.py` or `debug_*.py` scripts** — These were one-off debugging scripts and should not be in the repo.

4. **Any `__pycache__/` directories**

5. **Any `.pyc` files**

## What to Keep

Keep these (they are working tools or pending tasks):
- `cpk_extract.py` — Working CPK video extractor
- `pcm_extract.py` — PCM audio extractor (if present)
- Any `.md` task/prompt files in the repo root (not in `tools/`)

## Process

1. `git clone https://github.com/blythos/atolm.git` (or `git pull` if already cloned)
2. List everything in `tools/` and document what's there
3. Identify files matching the deletion criteria above
4. Delete them with `git rm`
5. Commit with message: `chore: clean up failed viewer and debugging scripts`
6. Push

## Validation

After cleanup, `tools/` should contain only:
- Working, tested extraction tools
- No viewer/browser code
- No test/debug scripts
- No `__pycache__`

List the final contents of `tools/` to confirm.
