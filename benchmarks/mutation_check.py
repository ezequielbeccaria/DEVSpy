"""Mutation check for the PDEVS oracle: inject known kernel bugs one at a time and
confirm tests/test_reference_pdevs.py fails for each. Restores every file.

usage (repo root): poetry run python benchmarks/mutation_check.py
"""
import importlib.util
import os
import pathlib
import subprocess
import sys

C = pathlib.Path("src/devspy/simulation/coordinator.py")
A = pathlib.Path("src/devspy/modeling/atomic.py")
D = pathlib.Path("src/devspy/modeling/digraph.py")
R = pathlib.Path("src/devspy/simulation/real_time.py")
M = [
  ("confluent -> deltext", C, "model.deltcon(time - sim.t_l, x_bag)", "model.deltext(time - sim.t_l, x_bag)"),
  ("default deltcon old e", A, "self.deltext(0, x)", "self.deltext(e, x)"),
  ("receivers not transitioned", C, "others = [s for s in receivers if s.t_n != time]", "others = []"),
  ("stale heap entries used", C, "if sim.version == version and tn == time:", "if tn == time:"),
  ("e measured from t_n", C, "model.deltext(time - sim.t_l, x_bag)", "model.deltext(sim.t_n - sim.t_l, x_bag)"),
  ("one value per port", C, "                            lst.extend(values)", "                            pass"),
  ("imminents skip ta()", C, "tn = time + (model.sigma if sim.ta_is_sigma else model.ta())", "tn = time + (model.sigma if sim.ta_is_sigma else model.ta()) + (0.5 if sim.index == 1 else 0)"),
  ("injection skips λ", C, "            self.compute_input_output(time)\n        self._send_down_messages()", "            self._imminent = self._pop(time)\n        self._send_down_messages()"),
  ("skip reschedule of imminents too", C, "if tn == old_tn != time:", "if tn == old_tn:"),
  ("heap rebuilt with stale versions", C, "heap = [(s.t_n, s.index, s.version) for s in self.simulators if s.t_n < INFINITY]", "heap = [(s.t_n, s.index, s.version - 1) for s in self.simulators if s.t_n < INFINITY]"),
  ("structure change applied mid-round", C, "        if self._running:\n            self._structure_pending = True", "        if False:\n            self._structure_pending = True"),
  ("new atomics start at t=0", C, "                sim.t_n = t + model.ta()", "                sim.t_n = model.ta()"),
  ("restructure loses existing state", C, "                    sim = reuse.pop(id(c), None) if reuse else None", "                    sim = None"),
  ("removal keeps couplings", D, "        for src, dst in dropped:\n            self._couprel.remove(src, dst)", "        pass"),
  ("real time: input delivered at the last event", R, "self._deliver(item, max(min(now_t, sim.next_tn(), until), sim.t_l))", "self._deliver(item, sim.t_l)"),
  ("real time: pacing ignores speed", R, "else (horizon - now_t) / self.speed", "else (horizon - now_t)"),
  ("scheduler: switch without rebuilding the heap", C, "        self._rebuild_heap()  # from the simulators' t_n (empty in scan mode)", "        pass"),
  ("scheduler: scan finds overdue models too", C, "return [s for s in self.simulators if s.t_n == time]", "return [s for s in self.simulators if s.t_n <= time + 0.25]"),
  ("root output dropped", C, "inp = root_out if dsim is None else dsim.input", "inp = {} if dsim is None else dsim.input"),
]
for name, path, old, new in M:
    src = path.read_text()
    assert old in src, name
    path.write_text(src.replace(old, new, 1))
    try:
        tests = ["tests/test_reference_pdevs.py", "tests/test_real_time.py"]
        cmd = [sys.executable, "-m", "pytest", "-q", "-x", *tests]
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        r = subprocess.run(cmd, capture_output=True, text=True, env=env)
        print(f"{'CAUGHT' if r.returncode else 'MISSED'}  {name}")
    finally:
        path.write_text(src)
        # A same-length mutation restored within the same second would leave a
        # .pyc that still looks fresh (mtime + size): drop it.
        pathlib.Path(importlib.util.cache_from_source(str(path))).unlink(missing_ok=True)
