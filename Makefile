# atolm — Panzer Dragoon Saga matching decompilation
# See docs/MAKEFILE_DESIGN.md for the design this implements.

SHELL := /bin/bash
PYTHON := python3
.DEFAULT_GOAL := all

.PHONY: all setup extract check check-functions tripwire clean

# --- setup: toolchain images + vendored proprietary compiler (no disc) -----
setup:
	docker build -t atolm-shc toolchain/shc/
	docker build -t atolm-cygnus toolchain/cygnus/
	toolchain/fetch-shc.sh

# --- extract: ISOs/ -> extracted/, hash-gated by config/targets/*.yaml -----
extract:
	$(PYTHON) tools/extract.py

# --- build: compile matched units, splice placeholders, assemble PRGs ------
all:
	$(PYTHON) tools/build_target.py

# --- check: full-PRG byte-identity (local only; needs the disc) -------------
check:
	$(PYTHON) tools/check.py

# --- check-functions: per-unit hash proofs (CI-safe, no disc needed) --------
check-functions:
	$(PYTHON) tools/check_units.py

tripwire:
	@echo "make tripwire: not implemented yet (Bucket 1 step 5)"; exit 1

clean:
	rm -rf build/
