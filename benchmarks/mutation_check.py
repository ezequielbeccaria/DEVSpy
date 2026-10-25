"""Mutation check for the PDEVS oracle: inject known kernel bugs one at a time and
confirm tests/test_reference_pdevs.py fails for each. Restores every file.

usage (repo root): poetry run python benchmarks/mutation_check.py
"""
import pathlib
import subprocess
import sys

C = pathlib.Path("src/devspy/simulation/coordinator.py")
A = pathlib.Path("src/devspy/modeling/atomic.py")
M = [
  ("confluent -> deltext", C, "model.deltcon(time - sim.t_l, x_bag)", "model.deltext(time - sim.t_l, x_bag)"),
  ("default deltcon old e", A, "self.deltext(0.0, x)", "self.deltext(e, x)"),
  ("receivers not transitioned", C, "others = [s for s in receivers if s.t_n != time]", "others = []"),
  ("stale heap entries used", C, "if sim.version == version and tn == time:", "if tn == time:"),
  ("e measured from t_n", C, "model.deltext(time - sim.t_l, x_bag)", "model.deltext(sim.t_n - sim.t_l, x_bag)"),
  ("one value per port", C, "                            lst.extend(values)", "                            pass"),
  ("imminents skip ta()", C, "tn = time + (model.sigma if sim.ta_is_sigma else model.ta())", "tn = time + (model.sigma if sim.ta_is_sigma else model.ta()) + (0.5 if sim.index == 1 else 0)"),
  ("injection skips λ", C, "            self.compute_input_output(time)\n        self._send_down_messages()", "            self._imminent = self._pop(time)\n        self._send_down_messages()"),
  ("skip reschedule of imminents too", C, "if tn == old_tn != time:", "if tn == old_tn:"),
  ("heap rebuilt with stale versions", C, "heap = [(s.t_n, s.index, s.version) for s in self.simulators if s.t_n < INFINITY]", "heap = [(s.t_n, s.index, s.version - 1) for s in self.simulators if s.t_n < INFINITY]"),
  ("root output dropped", C, "inp = root_out if dsim is None else dsim.input", "inp = {} if dsim is None else dsim.input"),
]
for name, path, old, new in M:
    src = path.read_text()
    assert old in src, name
    path.write_text(src.replace(old, new, 1))
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "tests/test_reference_pdevs.py"], capture_output=True, text=True)
        print(f"{'CAUGHT' if r.returncode else 'MISSED'}  {name}")
    finally:
        path.write_text(src)
