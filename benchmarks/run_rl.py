"""RL-style scenarios; appends to results/rl.jsonl.

  single:   one process, E episodes; end-to-end wall (startup included) + in-process times
  parallel: P concurrent worker processes x E episodes each (as RL actors do);
            aggregate wall, episodes/s and summed peak RSS

usage: python run_rl.py ENGINE ... [--reps N]
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

SINGLE = [(8, 20, 200.0), (8, 500, 200.0), (64, 100, 200.0)]
PARALLEL = [1, 4, 8, 16]
PAR_CFG = (8, 200, 200.0)


def cmd_for(engine, m, e, h):
    args = [str(m), str(e), str(h)]
    if engine == "devsjava":
        cp = open(os.path.join(HERE, "java", "classpath.txt")).read().strip()
        return [JAVA, *JAVA_OPTS, "-cp", cp, "RLBench", *args]
    return [sys.executable, os.path.join(HERE, "rl_bench.py"), *args]


def run_procs(cmds):
    t0 = time.perf_counter()
    procs = [subprocess.Popen(c, stdout=subprocess.PIPE, text=True) for c in cmds]
    rss, outs = [], []
    for p in procs:
        _, status, ru = os.wait4(p.pid, 0)
        assert status == 0
        rss.append(ru.ru_maxrss / 1024)
        outs.append(json.loads(p.stdout.read().strip().splitlines()[-1]))
    return (time.perf_counter() - t0) * 1e3, rss, outs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("engines", nargs="+")
    ap.add_argument("--reps", type=int, default=3)
    a = ap.parse_args()
    out = open(os.path.join(HERE, "results", "rl.jsonl"), "a")
    date = dt.datetime.now().isoformat(timespec="seconds")
    for engine in a.engines:
        label = JAVA_LABEL if engine == "devsjava" else f"devspy@{_git_sha(os.path.join(HERE, '..'))}"
        for m, e, h in SINGLE:
            runs = [run_procs([cmd_for(engine, m, e, h)]) for _ in range(a.reps)]
            inner = runs[0][2][0]
            row = {"scenario": "single", "label": label, "sections": m, "episodes": e,
                   "horizon": h, "decisions": inner["decisions"], "reward": inner["reward"],
                   "wall_ms_median": statistics.median(r[0] for r in runs),
                   "run_ms_median": statistics.median(r[2][0]["run_ms"] for r in runs),
                   "first_ep_ms": statistics.median(r[2][0]["first_ep_ms"] for r in runs),
                   "ep_ms_median": statistics.median(r[2][0]["ep_ms_median"] for r in runs),
                   "rss_mib": statistics.median(r[1][0] for r in runs), "date": date}
            out.write(json.dumps(row) + "\n")
            print(f"{label:22s} single m={m} E={e}: wall={row['wall_ms_median']:.0f}ms "
                  f"run={row['run_ms_median']:.0f}ms ep={row['ep_ms_median']:.2f}ms "
                  f"first={row['first_ep_ms']:.1f}ms rss={row['rss_mib']:.0f}MiB "
                  f"dec={row['decisions']} rew={row['reward']}", flush=True)
        m, e, h = PAR_CFG
        for p in PARALLEL:
            runs = [run_procs([cmd_for(engine, m, e, h)] * p) for _ in range(a.reps)]
            wall = statistics.median(r[0] for r in runs)
            row = {"scenario": "parallel", "label": label, "workers": p, "sections": m,
                   "episodes_per_worker": e, "horizon": h, "wall_ms_median": wall,
                   "episodes_per_s": p * e / (wall / 1e3),
                   "rss_total_mib": statistics.median(sum(r[1]) for r in runs), "date": date}
            out.write(json.dumps(row) + "\n")
            print(f"{label:22s} parallel P={p:2d}: wall={wall:.0f}ms "
                  f"eps/s={row['episodes_per_s']:.0f} rss_total={row['rss_total_mib']:.0f}MiB",
                  flush=True)


if __name__ == "__main__":
    main()
