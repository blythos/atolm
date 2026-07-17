"""Shared helpers for the manifest-driven build/check tools."""
import glob
import hashlib
import os
import subprocess

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The five segment states (Bucket 2 vocabulary). Progress is always reported
# as the full split across these — the matched figure is never shown alone.
SEGMENT_STATES = ("matched", "attempted", "unattempted", "data",
                  "library-candidate")
CODE_STATES = ("matched", "attempted", "unattempted", "library-candidate")
UNIT_STATUSES = ("matched", "attempted", "unattempted")


def validate_manifest(m):
    """Schema/consistency checks shared by all tools. Returns error strings.

    Enforced invariants:
    - unit status ∈ UNIT_STATUSES; `attempted` requires a `findings:` path
      that exists (attempted = residual WITH analysis on file, structurally)
    - segment state ∈ SEGMENT_STATES; matched/attempted segments must name a
      unit whose status agrees (single source of truth, disagreement fatal)
    - segment map, when present, is ordered and covers [0, size) exactly
    """
    errs = []
    target = m.get("target", "?")
    units = m.get("units") or {}
    for name, unit in units.items():
        if unit["status"] not in UNIT_STATUSES:
            errs.append(f"{target}: unit {name}: unknown status "
                        f"{unit['status']!r} (want {'|'.join(UNIT_STATUSES)})")
        if unit["status"] == "attempted":
            findings = unit.get("findings")
            if not findings:
                errs.append(f"{target}: unit {name}: status attempted "
                            f"requires findings: (analysis on file)")
            elif not os.path.exists(os.path.join(REPO, findings)):
                errs.append(f"{target}: unit {name}: findings file "
                            f"{findings} does not exist")
    segments = m.get("segments") or []
    for seg in segments:
        where = f"{target}: segment {seg.get('start', 0):#x}"
        state = seg.get("state")
        if state not in SEGMENT_STATES:
            errs.append(f"{where}: unknown state {state!r} "
                        f"(want {'|'.join(SEGMENT_STATES)})")
            continue
        if state in ("matched", "attempted"):
            uname = seg.get("unit")
            if uname not in units:
                errs.append(f"{where}: state {state} requires unit: "
                            f"naming a record in units")
            elif units[uname]["status"] != state:
                errs.append(f"{where}: state {state} but unit {uname} "
                            f"has status {units[uname]['status']!r} "
                            f"(segment state and unit status must agree)")
    if segments:
        if segments[0]["start"] != 0 or segments[-1]["end"] != m["size"]:
            errs.append(f"{target}: segment map must cover [0, size)")
        for a, b in zip(segments, segments[1:]):
            if a["end"] != b["start"]:
                errs.append(f"{target}: segment map gap/overlap at "
                            f"{a['end']:#x}")
    return errs


def segment_stats(m):
    """Per-state (count, bytes) across the segment map."""
    stats = {s: [0, 0] for s in SEGMENT_STATES}
    for seg in m.get("segments") or []:
        stats[seg["state"]][0] += 1
        stats[seg["state"]][1] += seg["end"] - seg["start"]
    return stats


def format_split(m):
    """The full five-state byte split, for every progress line we print."""
    stats = segment_stats(m)
    return ", ".join(f"{s} {stats[s][1]}" for s in SEGMENT_STATES)


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
