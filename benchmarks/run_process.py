"""End-to-end process cost (startup + build + simulate) and peak RSS per engine.
Appends to results/process.jsonl.

usage: python run_process.py ENGINE[=SRC] ... [--reps N]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_devstone import HERE, JAVA, JAVA_LABEL, JAVA_OPTS, _git_sha  # noqa: E402

CONFIGS = [(5, 3, 100), (10, 10, 1000)]


def measure(cmd, env):
    t0 = time.perf_counter()
    p = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL)
    _, status, ru = os.wait4(p.pid, 0)
    wall = time.perf_counter() - t0
    assert status == 0, cmd
    return wall * 1e3, ru.ru_maxrss  # KiB on Linux


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("engines", nargs="+")
    ap.add_argument("--reps", type=int, default=5)
    a = ap.parse_args()
    out = open(os.path.join(HERE, "results", "process.jsonl"), "a")
    for spec in a.engines:
        engine, _, src = spec.partition("=")
        env = dict(os.environ)
        for w, d, n in CONFIGS:
            args = [str(w), str(d), str(n), "1"]
            if engine == "devsjava":
                cp = open(os.path.join(HERE, "java", "classpath.txt")).read().strip()
                cmd, label = [JAVA, *JAVA_OPTS, "-cp", cp, "DevStone", *args], JAVA_LABEL
            else:
                cmd = [sys.executable, os.path.join(HERE, "devstone.py"), *args]
                if src:
                    env["PYTHONPATH"] = os.path.join(src, "src")
                label = f"devspy@{_git_sha(src or os.path.join(HERE, '..'))}"
            runs = [measure(cmd, env) for _ in range(a.reps)]
            row = {"label": label, "w": w, "d": d, "n": n,
                   "wall_ms": [r[0] for r in runs], "maxrss_kib": [r[1] for r in runs],
                   "wall_ms_median": statistics.median(r[0] for r in runs),
                   "maxrss_mib_median": statistics.median(r[1] for r in runs) / 1024,
                   "date": dt.datetime.now().isoformat(timespec="seconds")}
            out.write(json.dumps(row) + "\n")
            print(f"{label:28s} {(w, d, n)} wall={row['wall_ms_median']:.0f}ms "
                  f"rss={row['maxrss_mib_median']:.1f}MiB", flush=True)


if __name__ == "__main__":
    main()
