"""Record a full DEVS trace (every λ and δ, with time, e and bags) for a set of
models, and print one digest per model. Run it against two versions of the
engine (e.g. via PYTHONPATH) and diff the output to prove they are
observationally identical.

usage: python trace_diff.py [N_RANDOM] [--model-level]

--model-level instruments the user's Atomic subclasses instead of the simulator
classes. Use it for engine builds whose simulators cannot be monkeypatched
(e.g. compiled with mypyc); it records the same λ/δ events, with the time taken
from the model's simulator.
"""
from __future__ import annotations

import hashlib
import os
import random
import sys

from devspy import Atomic, Bag, DevsSuiteFacade, Digraph
from devspy.simulation.atomic_simulator import AtomicSimulator

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "examples"))
sys.path.insert(0, HERE)

TRACE: list[str] = []


def _bag(x: Bag) -> str:
    return "[" + ",".join(sorted(f"{port}={v!r}" for port, vals in x.items() for v in vals)) + "]"


# --- instrumentation: wrap the atomic-level primitives, which neither version changed
_orig_wrap = AtomicSimulator.wrap_deltfunc
_orig_cio = AtomicSimulator.compute_input_output


def _wrap(self, t, x=None):
    m = self.my_model
    bag = self.input if x is None else x
    kind = None
    if bag and t == self.t_n:
        kind = "con"
    elif t == self.t_n:
        kind = "int"
    elif bag:
        kind = "ext"
    if kind:
        TRACE.append(f"{t:.9g} {m.get_name()} {kind} e={t - self.t_l:.9g} x={_bag(bag)}")
    return _orig_wrap(self, t, x)


def _cio(self, t):
    _orig_cio(self, t)
    if self.output:
        TRACE.append(f"{t:.9g} {self.my_model.get_name()} out y={_bag(self.output)}")


def _instrument_models():
    def all_subclasses(cls):
        for sub in cls.__subclasses__():
            yield sub
            yield from all_subclasses(sub)

    def t_of(model):
        sim = model.get_simulator()
        return sim.t_n if sim is not None else float("nan")

    for cls in set(all_subclasses(Atomic)):
        def wrap(cls=cls):
            d_int, d_ext, d_con, out = cls.deltint, cls.deltext, cls.deltcon, cls.out

            def deltint(self):
                TRACE.append(f"{t_of(self):.9g} {self.get_name()} int")
                return d_int(self)

            def deltext(self, e, x):
                sim = self.get_simulator()
                t = sim.t_l + e if sim is not None else float("nan")
                TRACE.append(f"{t:.9g} {self.get_name()} ext e={e:.9g} x={_bag(x)}")
                return d_ext(self, e, x)

            def deltcon(self, e, x):
                TRACE.append(f"{t_of(self):.9g} {self.get_name()} con e={e:.9g} x={_bag(x)}")
                # nested deltint/deltext calls are traced too; keep them, they are part of the behaviour
                return d_con(self, e, x)

            def out_(self):
                y = out(self)
                if y:
                    TRACE.append(f"{t_of(self):.9g} {self.get_name()} out y={_bag(y)}")
                return y

            cls.deltint, cls.deltext, cls.deltcon, cls.out = deltint, deltext, deltcon, out_
        wrap()


if "--model-level" not in sys.argv:
    AtomicSimulator.wrap_deltfunc = _wrap
    AtomicSimulator.compute_input_output = _cio


# --- random hierarchical models with ties, zero-time advances and confluence
class RndAtomic(Atomic):
    def __init__(self, name, rng: random.Random, n_out):
        super().__init__(name)
        self.add_inport("in")
        self.delays = [rng.choice([0, 1, 1, 2, 3]) for _ in range(5)]
        self.n_out = n_out
        for i in range(n_out):
            self.add_outport(f"o{i}")

    def initialize(self):
        self.acc, self.k = 0, 0
        self.hold_in("active", self.delays[0] + 1)

    def _next(self):
        self.k += 1
        d = self.delays[(self.acc + self.k) % len(self.delays)]
        if self.k > 12:
            self.passivate()
        else:
            self.hold_in("active", d)

    def deltint(self):
        self._next()

    def deltext(self, e, x):
        self.acc += sum(v for vals in x.values() for v in vals) + int(e * 10)
        if self.acc % 3 == 0:
            self.cont(e)
        else:
            self._next()

    def deltcon(self, e, x):
        self.acc += 7
        self.deltint()
        self.deltext(0.0, x)

    def out(self):
        return {f"o{i}": [self.acc + self.k + i] for i in range(self.n_out)}


def random_model(seed: int) -> Digraph:
    rng = random.Random(seed)
    counter = [0]

    def build(depth) -> Digraph:
        g = Digraph(f"G{counter[0]}")
        counter[0] += 1
        g.add_inport("in")
        g.add_outport("out")
        kids = []
        for _ in range(rng.randint(1, 4)):
            if depth > 0 and rng.random() < 0.35:
                kids.append(build(depth - 1))
            else:
                a = RndAtomic(f"A{counter[0]}", rng, rng.randint(1, 2))
                counter[0] += 1
                kids.append(a)
        for k in kids:
            g.add(k)
        def outs(k):
            return k.get_outports() if isinstance(k, Atomic) else ["out"]

        for k in kids:  # EIC
            if rng.random() < 0.5:
                g.add_coupling(g, "in", k, "in")
        for src in kids:  # IC (no self-loops: DEVS forbids them)
            for dst in kids:
                if src is not dst and rng.random() < 0.4:
                    g.add_coupling(src, rng.choice(outs(src)), dst, "in")
        src = rng.choice(kids)  # EOC
        g.add_coupling(src, rng.choice(outs(src)), g, "out")
        return g

    top = build(3)
    return top


def run_digraph(model, end):
    f = DevsSuiteFacade(model)
    f.reset()
    f.simulate_to_time(end)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    n_random = int(args[0]) if args else 200
    cases = []

    import gpt_model
    import manufacturing_line
    import mm1_queue
    import devstone_model as ds

    if "--model-level" in sys.argv:
        _instrument_models()

    cases.append(("gpt", lambda: gpt_model.run(end_time=30.0)))
    cases.append(("mm1", lambda: mm1_queue.run(seed=1, end_time=500.0)))
    cases.append(("manufacturing", lambda: manufacturing_line.run()))

    for w, d in [(5, 3), (3, 6), (8, 1)]:
        cases.append((f"devstone{w}x{d}", lambda w=w, d=d: run_digraph(ds.build(w, d, 30), 1e9)))
    for s in range(n_random):
        cases.append((f"random{s}", lambda s=s: run_digraph(random_model(s), 60.0)))

    total = hashlib.sha256()
    for name, fn in cases:
        TRACE.clear()
        random.seed(12345)
        fn()
        h = hashlib.sha256("\n".join(TRACE).encode()).hexdigest()[:16]
        total.update(h.encode())
        print(f"{name:16s} events={len(TRACE):6d} sha={h}")
    print(f"ALL {total.hexdigest()[:16]}")


if __name__ == "__main__":
    main()
