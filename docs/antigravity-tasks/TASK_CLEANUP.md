# Task: Clean Up tools/ Directory

The `tools/` directory currently contains 9 files, but only 1 is an actual tool. The rest are debugging scripts and failed experiments from the CPK extraction process. They should never have been committed to master.

## Action Required

### Delete these files (they are debugging artifacts, not tools):
- `tools/cpk_extract_old.py` — superseded by cpk_extract.py
- `tools/adpcm.py` — ADPCM decoder from incorrect audio hypothesis
- `tools/adpcm_brute.py` — brute-force parameter search (debugging)
- `tools/analyze_vol.py` — volume analysis debugging script
- `tools/debug_adpcm.py` — ADPCM debugging script
- `tools/debug_cpk_audio.py` — CPK audio debugging script
- `tools/debug_sector.py` — sector reading debugging script
- `tools/yamaha_adpcm.py` — Yamaha ADPCM decoder from incorrect hypothesis

### Keep:
- `tools/cpk_extract.py` — the working CPK extractor

### Add:
- `tools/__init__.py` — empty file (makes tools/ a Python package for shared imports)
- `tools/common/__init__.py` — empty file
- `tools/common/iso9660.py` — extract the ISO9660 disc reader code from cpk_extract.py into a shared module so all future tools reuse the same disc reading code
- `tools/common/saturn.py` — shared Saturn utilities (endian conversion, fixed-point math, RGB555 decoding) that will be used by multiple tools
- `tools/README.md` — brief description of each tool and how to run it

### Final structure should be:
```
tools/
├── __init__.py
├── README.md
├── cpk_extract.py          # CPK/Sega FILM video extractor
├── common/
│   ├── __init__.py
│   ├── iso9660.py          # Shared ISO9660 disc reader
│   └── saturn.py           # Shared Saturn format utilities
```

Future tools (pcm_extract.py, model_viewer/, etc.) will go alongside cpk_extract.py and import from common/.

### Rules for future commits:
- **Never commit debugging scripts to master.** Use a local `scratch/` directory (already in .gitignore) or a feature branch.
- **Never commit `_old` versions of files.** Use git history to access previous versions.
- **One tool = one file** (or one subdirectory for complex tools like the model viewer).

Commit message: `[tools] Clean up tools directory, extract shared modules`
