"""The flat kernel against the literal PDEVS abstract simulator in reference_pdevs.

Random hierarchical models (ties, zero-time advances, confluent events, fan-in
and fan-out through several levels, default and custom deltcon) are run by both
engines. Each atomic logs every transition from its own point of view (its
clock, the kind, e and the input bag as a sorted multiset). Because a bag is a
multiset and simultaneous transitions of different models commute, the
comparison is per model and order-insensitive within a bag. The root outputs
must match too.
"""

import random

import pytest

from devspy import Atomic, DevsSuiteFacade, Digraph
from tests import reference_pdevs


def _multiset(bag):
    return tuple(sorted((port, tuple(sorted(values))) for port, values in bag.items() if values))


class RndAtomic(Atomic):
    def __init__(self, name, rng: random.Random, log):
        super().__init__(name)
        self.delays = [rng.choice([0, 0.5, 1, 1, 2, 3]) for _ in range(6)]
        self.n_in = rng.randint(1, 2)
        self.n_out = rng.randint(1, 2)
        self.custom_con = rng.random() < 0.5
        self.uses_cont = rng.random() < 0.5
        self.log = log.setdefault(name, [])
        for i in range(self.n_in):
            self.add_inport(f"i{i}")
        for i in range(self.n_out):
            self.add_outport(f"o{i}")

    def initialize(self):
        self.acc, self.k, self.clock = 0, 0, 0.0
        self.log.clear()
        self.hold_in("active", self.delays[0] + 1)

    def _next(self):
        self.k += 1
        if self.k > 10:
            self.passivate()
        else:
            self.hold_in("active", self.delays[(self.acc + self.k) % len(self.delays)])

    def deltint(self):
        self.clock += self.sigma
        self.log.append((self.clock, "int"))
        self._next()

    def deltext(self, e, x):
        self.clock += e
        self.log.append((self.clock, "ext", e, _multiset(x)))
        self.acc += sum(v for values in x.values() for v in values)
        if self.uses_cont and self.acc % 3:
            self.cont(e)
        else:
            self._next()

    def deltcon(self, e, x):
        if not self.custom_con:
            super().deltcon(e, x)  # deltint(); deltext(0, x)
            return
        self.clock += e
        self.log.append((self.clock, "con", e, _multiset(x)))
        self.acc += 7 + len(x)
        self._next()

    def out(self):
        return {f"o{i}": [self.acc + self.k + i] for i in range(self.n_out)}


def random_model(seed):
    rng = random.Random(seed)
    log = {}
    counter = [0]

    def build(depth):
        g = Digraph(f"G{counter[0]}")
        counter[0] += 1
        g.add_inport("in")
        g.add_outport("out")
        kids = []
        for _ in range(rng.randint(1, 4)):
            if depth > 0 and rng.random() < 0.35:
                kids.append(build(depth - 1))
            else:
                kids.append(RndAtomic(f"A{counter[0]}", rng, log))
                counter[0] += 1
        for k in kids:
            g.add(k)

        def ins(k):
            return k.get_inports()

        def outs(k):
            return k.get_outports()

        for k in kids:  # EIC
            if rng.random() < 0.5:
                g.add_coupling(g, "in", k, rng.choice(ins(k)))
        for src in kids:  # IC between distinct components
            for dst in kids:
                if src is not dst and rng.random() < 0.4:
                    g.add_coupling(src, rng.choice(outs(src)), dst, rng.choice(ins(dst)))
        for _ in range(rng.randint(1, 2)):  # EOC
            src = rng.choice(kids)
            g.add_coupling(src, rng.choice(outs(src)), g, "out")
        return g

    top = build(3)
    top.add_outport("out")
    return top, log


def _run_devspy(seed, end, heap_limit=None):
    model, log = random_model(seed)
    f = DevsSuiteFacade(model)
    f.reset()
    sim = f.get_simulator()
    if heap_limit is not None:
        sim._heap_limit = heap_limit
    outputs = []
    sim.show_output = lambda: outputs.append((sim.t_l, _multiset(sim.output)))
    f.simulate_to_time(end)
    return log, outputs


def _run_reference(seed, end):
    model, log = random_model(seed)
    outputs = [(t, _multiset(y)) for t, y in reference_pdevs.run(model, end)]
    return log, outputs


@pytest.mark.parametrize("seed", range(300))
def test_kernel_matches_reference_abstract_simulator(seed):
    log, outputs = _run_devspy(seed, 40.0)
    ref_log, ref_outputs = _run_reference(seed, 40.0)
    assert log == ref_log
    assert outputs == ref_outputs
    assert any(log.values())  # the model actually did something


@pytest.mark.parametrize("seed", range(100))
def test_kernel_matches_reference_with_eager_heap_rebuilds(seed):
    # _heap_limit = 0 rebuilds the heap after every round (normally only once
    # stale entries pile up, which these small models never reach).
    log, outputs = _run_devspy(seed, 40.0, heap_limit=0)
    ref_log, ref_outputs = _run_reference(seed, 40.0)
    assert log == ref_log
    assert outputs == ref_outputs


def _with_root_input(model):
    model.add_inport("in")
    for c in model.get_components():
        model.add_coupling(model, "in", c, c.get_inports()[0])
    return model


@pytest.mark.parametrize("seed", range(150))
def test_external_injections_match_reference(seed):
    # Injection times on a 0.25 grid: many coincide with internal events, which
    # makes the injection a confluent round ((*, t) then (x, t)).
    rng = random.Random(1000 + seed)
    times = sorted({rng.randrange(0, 160) / 4 for _ in range(rng.randint(1, 8))})
    injections = [(t, {"in": [rng.randint(1, 9) for _ in range(rng.randint(1, 3))]}) for t in times]

    model, log = random_model(seed)
    f = DevsSuiteFacade(_with_root_input(model))
    f.reset()
    sim = f.get_simulator()
    outputs = []
    sim.show_output = lambda: outputs.append((sim.t_l, _multiset(sim.output)))
    for t, bag in injections:
        while sim.next_tn() < t:  # every round strictly before t
            f.simulate_iterations(1)
        sim.sim_inject(t - sim.t_l, bag)
    f.simulate_to_time(40.0)

    ref_model, ref_log = random_model(seed)
    ref_outputs = reference_pdevs.run(_with_root_input(ref_model), 40.0, injections)
    assert log == ref_log
    assert outputs == [(t, _multiset(y)) for t, y in ref_outputs]


def test_reset_replays_like_a_fresh_reference_run():
    model, log = random_model(7)
    f = DevsSuiteFacade(model)
    for _ in range(3):
        f.reset()
        f.simulate_to_time(40.0)
        assert log == _run_reference(7, 40.0)[0]


def test_reference_reproduces_the_hand_checked_gpt_trace():
    """The oracle itself against the hand-derived trace of tests/test_parity_gpt.py."""
    from examples.gpt_model import build

    gpt, trans = build()
    reference_pdevs.run(gpt, 30.0)
    assert trans.arrivals == [(2.0 * k, k) for k in range(1, 11)]
    assert trans.completions == [(5.0, 1), (9.0, 3), (13.0, 5), (17.0, 7), (21.0, 9)]
