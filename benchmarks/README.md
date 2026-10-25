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
| `other_python/` | xDEVS.py and PythonPDEVS (minimal kernel) ports of both models, plus `bench.py` |
| `cpp/` | adevs and Cadmium v2 ports of both models (`adevs_bench.cpp`, `cadmium_bench.cpp`) |
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

### Other engines

Third-party engines are not dependencies of DEVSpy. Install them in a separate venv and point
the runners at it:

```bash
python -m venv /tmp/others && /tmp/others/bin/pip install xdevs==3.0.0 -e .
# PythonPDEVS 2.4.1 is Python 2 code: convert a copy of github.com/capocchi/PythonPDEVS
cp -r PythonPDEVS/src /tmp/pypdevs-py3
python3.12 -m lib2to3 -w -n /tmp/pypdevs-py3/pypdevs/minimal.py /tmp/pypdevs-py3/pypdevs/schedulers
# C++: header checkouts of github.com/smiz/adevs and github.com/SimulationEverywhere/cadmium_v2
ADEVS_HOME=... CADMIUM_HOME=... cpp/build.sh

export OTHERS_PY=/tmp/others/bin/python PYPDEVS_PATH=/tmp/pypdevs-py3
python benchmarks/run_devstone.py xdevs xdevs-flat pypdevs-minimal adevs cadmium
python benchmarks/run_rl.py xdevs pypdevs-minimal adevs cadmium
```

To benchmark a compiled build of `devspy.simulation`, compile it into a copy of `src/` (see
`FINDINGS.md`, "mypyc") and pass it as `devspy=/path/to/copy`.

## Checking semantics

To check that a change to the engine preserves semantics:

```bash
git worktree add /tmp/devspy-old <commit>
PYTHONPATH=/tmp/devspy-old/src python benchmarks/trace_diff.py > old.txt
python benchmarks/trace_diff.py > new.txt
diff old.txt new.txt
```

Add `--model-level` to instrument the user's atomic models instead of the simulator classes. Use
it for builds whose simulators cannot be monkeypatched (mypyc).
