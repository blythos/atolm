"""Shared helpers for the manifest-driven build/check tools."""
import glob
import hashlib
import os
import subprocess

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_manifests():
    out = []
    for path in sorted(glob.glob(os.path.join(REPO, "config/targets/*.yaml"))):
        with open(path) as f:
            out.append(yaml.safe_load(f))
    return out


def load_compilers():
    with open(os.path.join(REPO, "config/compilers.yaml")) as f:
        return yaml.safe_load(f)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def compile_unit(unit_name, unit, workdir):
    """Compile one unit in its toolchain container; return .text bytes.

    The source is copied to UNIT.C (8.3 uppercase — SHC is a '90s toolchain)
    in `workdir`, which is bind-mounted at /work in the container.
    """
    if unit["compiler"] != "shc-5.0-r31":
        raise NotImplementedError(f"{unit_name}: compiler {unit['compiler']}")
    os.makedirs(workdir, exist_ok=True)
    src = os.path.join(REPO, unit["source"])
    with open(src, "rb") as f, open(os.path.join(workdir, "UNIT.C"), "wb") as g:
        g.write(f.read())
    flags = " ".join(unit["flags"])
    subprocess.run(
        [os.path.join(REPO, "toolchain/shc/run.sh"), workdir,
         f"shc-compile UNIT.C unit {flags}"],
        check=True, capture_output=True)
    with open(os.path.join(workdir, "unit.bin"), "rb") as f:
        return f.read()


def verify_unit(unit_name, unit, workdir):
    """Compile a unit and check its proof. Returns (ok, got_bytes)."""
    data = compile_unit(unit_name, unit, workdir)
    size = unit["size"]
    ok = len(data) == size and sha256(data) == unit["sha256"]
    return ok, data
