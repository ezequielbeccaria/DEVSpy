"""Run the DEVStone-like matrix on several engines and append results to
results/devstone.jsonl (one JSON object per engine x config, plus metadata).

usage:
  python run_devstone.py ENGINE[=SRC] ... [--reps N] [--tag TAG]

ENGINE is one of:
  devspy          the devspy importable from this interpreter
  devspy=PATH     devspy from PATH/src (e.g. a git worktree of an older commit)
  devsjava        java/DevStone (run java/build.sh first)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIGS = [(5, 3, 1000), (10, 10, 1000), (200, 1, 1000), (3, 50, 500), (20, 20, 500)]
JAVA = os.environ.get("JAVA", "/usr/lib/jvm/jdk-17/bin/java")
JAVA_OPTS = os.environ.get("JAVA_OPTS", "").split()
# Other Python engines run in their own interpreter/venv (see other_python/).
OTHERS_PY = os.environ.get("OTHERS_PY", sys.executable)
# Interpreter running DEVSpy (sys.executable); labels note it unless it is the
# reference CPython 3.12 that all earlier results used.
PY = f"{sys.implementation.name}{sys.version_info.major}.{sys.version_info.minor}"
PY_SUFFIX = "" if PY == "cpython3.12" else f"[{PY}]"
PYPDEVS_PATH = os.environ.get("PYPDEVS_PATH", "")
OTHER_ENGINES = ("xdevs", "xdevs-flat", "pypdevs-minimal")
CPP_BIN = os.environ.get("CPP_BIN", os.path.join(HERE, "cpp", "bin"))
CPP_ENGINES = ("adevs", "cadmium")
JAVA_LABEL = "devsjava" + (f"[{' '.join(JAVA_OPTS)}]" if JAVA_OPTS else "")


def devspy_path(src):
    """PYTHONPATH entry for a DEVSpy checkout given as `devspy=<repo root>`.

    Refuses anything else: a wrong path would silently fall back to the
    installed devspy, and both sides of a comparison would run the same code."""
    path = os.path.join(src, "src")
    if not os.path.isfile(os.path.join(path, "devspy", "__init__.py")):
        raise SystemExit(f"devspy={src}: expected a DEVSpy repo root containing src/devspy/")
    return path


def devspy_label(src):
    """devspy@<sha>[+dirty] for git checkouts, devspy[<dir name>] otherwise."""
    sha = _git_sha(src or os.path.join(HERE, ".."))
    return f"devspy@{sha}" if sha else f"devspy[{os.path.basename(os.path.normpath(src))}]"


def _git_sha(path):
    try:
        sha = subprocess.check_output(["git", "-C", path, "rev-parse", "--short", "HEAD"],
                                      text=True).strip()
        dirty = subprocess.run(["git", "-C", path, "diff", "--quiet", "HEAD", "--", "src"]).returncode
        return sha + ("+dirty" if dirty else "")
    except Exception:
        return None


def run_one(engine, src, cfg, reps):
    w, d, n = cfg
    args = [str(w), str(d), str(n), str(reps)]
    env = dict(os.environ)
    if engine == "devsjava":
        cp = open(os.path.join(HERE, "java", "classpath.txt")).read().strip()
        cmd = [JAVA, *JAVA_OPTS, "-cp", cp, "DevStone", *args]
    elif engine in CPP_ENGINES:
        cmd = [os.path.join(CPP_BIN, f"{engine}_bench"), "devstone", *args]
    elif engine in OTHER_ENGINES:
        cmd = [OTHERS_PY, os.path.join(HERE, "other_python", "bench.py"), engine, "devstone", *args]
        env["PYTHONPATH"] = PYPDEVS_PATH
    else:
        cmd = [sys.executable, os.path.join(HERE, "devstone.py"), *args]
        if src:
            env["PYTHONPATH"] = devspy_path(src)
    out = subprocess.check_output(cmd, env=env, text=True)
    return json.loads(out.strip().splitlines()[-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("engines", nargs="+")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    meta = {
        "date": dt.datetime.now().isoformat(timespec="seconds"),
        "host": platform.node(), "cpu": platform.processor() or platform.machine(),
        "python": platform.python_version(), "tag": a.tag,
    }
    path = os.path.join(HERE, "results", "devstone.jsonl")
    with open(path, "a") as fh:
        for spec in a.engines:
            engine, _, src = spec.partition("=")
            label = (JAVA_LABEL if engine == "devsjava"
                     else engine if engine in OTHER_ENGINES + CPP_ENGINES
                     else devspy_label(src) + PY_SUFFIX)
            for cfg in CONFIGS:
                r = run_one(engine, src, cfg, a.reps)
                r.update(meta, label=label, python=PY)
                # JIT engines: first rep is cold; report warm median separately
                sims = r["sim_ms"]
                r["sim_ms_median"] = statistics.median(sims)
                r["sim_ms_warm_median"] = statistics.median(sims[1:]) if len(sims) > 1 else sims[0]
                fh.write(json.dumps(r) + "\n")
                print(f"{label:22s} {cfg}  median={r['sim_ms_median']:.1f}ms "
                      f"warm={r['sim_ms_warm_median']:.1f}ms  int={r['int']} ext={r['ext']} sink={r['sink']}",
                      flush=True)


if __name__ == "__main__":
    main()
