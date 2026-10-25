"""Render results/*.jsonl as markdown tables (latest row per label x config).

usage: python summarize.py > results/SUMMARY.md
"""
import json
import os
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    path = os.path.join(HERE, "results", name)
    if not os.path.exists(path):
        return []
    return [json.loads(line) for line in open(path)]


def latest(rows, key):
    d = OrderedDict()
    for r in rows:
        d[key(r)] = r
    return list(d.values())


def table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def main():
    ds = latest(load("devstone.jsonl"), lambda r: (r["label"], r["w"], r["d"], r["n"]))
    labels = list(OrderedDict.fromkeys(r["label"] for r in ds))
    cfgs = list(OrderedDict.fromkeys((r["w"], r["d"], r["n"]) for r in ds))
    by = {(r["label"], (r["w"], r["d"], r["n"])): r for r in ds}
    print("## DEVStone-like: simulation wall clock (ms, warm median)\n")
    rows = []
    for c in cfgs:
        any_r = next(by[(lb, c)] for lb in labels if (lb, c) in by)
        rows.append([f"{c[0]}x{c[1]}, {c[2]} ev", any_r["int"] + any_r["ext"]]
                    + [f"{by[(lb, c)]['sim_ms_warm_median']:.0f}" if (lb, c) in by else "-"
                       for lb in labels])
    print(table(["config", "transitions"] + labels, rows), "\n")

    pr = latest(load("process.jsonl"), lambda r: (r["label"], r["w"], r["d"], r["n"]))
    print("## End-to-end process (startup + build + run)\n")
    print(table(["engine", "config", "wall ms", "peak RSS MiB"],
                [[r["label"], f"{r['w']}x{r['d']}, {r['n']} ev", f"{r['wall_ms_median']:.0f}",
                  f"{r['maxrss_mib_median']:.1f}"] for r in pr]), "\n")

    rl = load("rl.jsonl")
    single = latest([r for r in rl if r["scenario"] == "single"],
                    lambda r: (r["label"], r["sections"], r["episodes"]))
    print("## RL-style: single worker\n")
    print(table(["engine", "sections", "episodes", "process wall ms", "ms/episode",
                 "1st episode ms", "RSS MiB", "decisions", "reward"],
                [[r["label"], r["sections"], r["episodes"], f"{r['wall_ms_median']:.0f}",
                  f"{r['ep_ms_median']:.2f}", f"{r['first_ep_ms']:.1f}", f"{r['rss_mib']:.0f}",
                  r["decisions"], r["reward"]] for r in single]), "\n")
    par = latest([r for r in rl if r["scenario"] == "parallel"], lambda r: (r["label"], r["workers"]))
    print("## RL-style: parallel workers (8 sections, 200 episodes/worker)\n")
    print(table(["engine", "workers", "wall ms", "episodes/s", "total RSS MiB"],
                [[r["label"], r["workers"], f"{r['wall_ms_median']:.0f}",
                  f"{r['episodes_per_s']:.0f}", f"{r['rss_total_mib']:.0f}"] for r in par]))


if __name__ == "__main__":
    main()
