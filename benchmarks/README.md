# Benchmarks

Performance comparisons between DEVSpy and other DEVS engines. Every engine
runs **the same model**, and each harness prints counters (transitions,
decisions, reward) that must match across engines, which proves the work done
is identical.

| File | What |
|---|---|
| `devstone_model.py` | DEVStone-LI-like model (generator → W×D hierarchy → sink) |
| `devstone.py` | Times that model on DEVSpy (one JSON line) |
| `rl_model.py`, `rl_bench.py` | RL-environment-shaped model: M track sections + an agent atomic deciding at every arrival; many short episodes with `reset()` |
| `java/` | DEVSJAVA (Devs-Suite-Facade) ports of both models: `DevStone.java`, `RLBench.java` |
| `trace_diff.py` | Records the full λ/δ trace of the examples, DEVStone and 200 random hierarchical models; diff the output of two engine versions to prove they are observationally identical |
| `run_devstone.py`, `run_process.py`, `run_rl.py` | Runners; append to `results/*.jsonl` |
| `summarize.py` | Renders `results/*.jsonl` into `results/SUMMARY.md` |
| `FINDINGS.md` | Running log of findings and conclusions |

## Running

```bash
java/build.sh                                   # needs ../../Devs-Suite-Facade built (mvn package) and a JDK
python benchmarks/run_devstone.py devspy devsjava
python benchmarks/run_devstone.py devspy=/path/to/old/worktree   # another DEVSpy version
python benchmarks/run_process.py devspy devsjava
python benchmarks/run_rl.py devspy devsjava
JAVA_OPTS="-XX:+UseSerialGC -Xmx128m" python benchmarks/run_rl.py devsjava
python benchmarks/summarize.py > benchmarks/results/SUMMARY.md
```

To check that a change to the engine preserves semantics:

```bash
git worktree add /tmp/devspy-old <commit>
PYTHONPATH=/tmp/devspy-old/src python benchmarks/trace_diff.py > old.txt
python benchmarks/trace_diff.py > new.txt
diff old.txt new.txt
```
