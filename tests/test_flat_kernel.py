"""Behaviour of the flattened coordinator across hierarchy levels."""

from devspy import Atomic, Content, DevsSuiteFacade, Digraph, IntEnt, Message


class Pulse(Atomic):
    """Emits its counter on `out` every `period` until `n` pulses."""

    def __init__(self, name, period=1.0, n=3):
        super().__init__(name)
        self.add_outport("out")
        self.period, self.n = period, n

    def initialize(self):
        self.k = 0
        self.hold_in("active", self.period)

    def deltint(self):
        self.k += 1
        if self.k >= self.n:
            self.passivate()
        else:
            self.hold_in("active", self.period)

    def out(self):
        m = Message()
        m.add(Content("out", IntEnt(self.k)))
        return m


class Recorder(Atomic):
    def __init__(self, name):
        super().__init__(name)
        self.add_inport("in")
        self.seen = []

    def initialize(self):
        self.seen = []
        self.passivate()

    def deltext(self, e, x):
        sim = self.get_simulator()
        self.seen.extend((sim.t_l + e, int(c.get_value())) for c in x)


def _wrap(name, inner, in_port=True, out_port=True):
    """Put `inner` alone inside a digraph that forwards in -> inner.in, inner.out -> out."""
    g = Digraph(name)
    g.add(inner)
    if in_port:
        g.add_inport("in")
        g.add_coupling(g, "in", inner, "in")
    if out_port:
        g.add_outport("out")
        g.add_coupling(inner, "out", g, "out")
    return g


def test_message_crosses_three_levels_up_and_down():
    pulse, rec = Pulse("p"), Recorder("r")
    src = _wrap("s1", _wrap("s2", _wrap("s3", pulse, in_port=False), in_port=False), in_port=False)
    dst = _wrap("d1", _wrap("d2", _wrap("d3", rec, out_port=False), out_port=False), out_port=False)
    top = Digraph("top")
    top.add(src)
    top.add(dst)
    top.add_coupling(src, "out", dst, "in")
    f = DevsSuiteFacade(top)
    f.reset()
    f.simulate_to_time(10.0)
    assert rec.seen == [(1.0, 0), (2.0, 1), (3.0, 2)]


def test_sim_inject_reaches_nested_atomic():
    rec = Recorder("r")
    top = _wrap("top", _wrap("mid", rec, out_port=False), out_port=False)
    f = DevsSuiteFacade(top)
    f.reset()
    f.get_simulator().sim_inject(2.5, "in", IntEnt(7))
    assert rec.seen == [(2.5, 7)]


def test_reset_reuses_the_model_and_replays_identically():
    pulse, rec = Pulse("p", n=4), Recorder("r")
    top = Digraph("top")
    top.add(pulse)
    top.add(rec)
    top.add_coupling(pulse, "out", rec, "in")
    f = DevsSuiteFacade(top)
    runs = []
    for _ in range(3):
        f.reset()
        f.simulate_to_time(10.0)
        runs.append(list(rec.seen))
    assert runs[0] == runs[1] == runs[2] == [(1.0, 0), (2.0, 1), (3.0, 2), (4.0, 3)]


def test_incremental_simulate_to_time_matches_one_shot():
    def build():
        pulse, rec = Pulse("p", period=0.5, n=10), Recorder("r")
        top = Digraph("top")
        top.add(pulse)
        top.add(rec)
        top.add_coupling(pulse, "out", rec, "in")
        return top, rec

    top, rec = build()
    f = DevsSuiteFacade(top)
    f.reset()
    for t in (1.0, 2.0, 3.0, 10.0):
        f.simulate_to_time(t)
    top2, rec2 = build()
    g = DevsSuiteFacade(top2)
    g.reset()
    g.simulate_to_time(10.0)
    assert rec.seen == rec2.seen and len(rec.seen) == 10


def test_deep_cloning_snapshot_runs_independently():
    pulse, rec = Pulse("p", n=5), Recorder("r")
    top = Digraph("top")
    top.add(pulse)
    top.add(rec)
    top.add_coupling(pulse, "out", rec, "in")
    f = DevsSuiteFacade(top)
    f.reset()
    f.simulate_to_time(2.0)
    clone = f.deep_cloning()
    f.simulate_to_time(10.0)
    clone.simulate(10.0)
    clone_rec = clone.simulators[1].get_model()
    assert clone_rec is not rec
    assert clone_rec.seen == rec.seen == [(1.0, 0), (2.0, 1), (3.0, 2), (4.0, 3), (5.0, 4)]


def test_input_coupled_straight_to_output_is_ignored():
    rec = Recorder("r")
    inner = Digraph("inner")
    inner.add_inport("in")
    inner.add_outport("out")
    inner.add(rec)
    inner.add_coupling(inner, "in", inner, "out")  # not a valid DEVS coupling
    pulse = Pulse("p", n=1)
    top = Digraph("top")
    top.add(pulse)
    top.add(inner)
    top.add_coupling(pulse, "out", inner, "in")
    f = DevsSuiteFacade(top)
    f.reset()
    f.simulate_to_time(5.0)
    assert rec.seen == []
