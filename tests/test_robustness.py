"""Model validation, zero-time loop guard, lazy initialization and strict injection."""

import pytest

from devspy import (
    Atomic,
    Bag,
    DevsSuiteFacade,
    Digraph,
    ModelStructureError,
    TimeAtomicSimulator,
    TimeCoordinator,
    ZeroTimeLoopError,
)


class Ticker(Atomic):
    def __init__(self, name="ticker", period=1.0):
        super().__init__(name)
        self.add_outport("tick")
        self.period = period
        self.inits = 0

    def initialize(self):
        self.inits += 1
        self.ticks = 0
        self.hold_in("active", self.period)

    def deltint(self):
        self.ticks += 1
        self.hold_in("active", self.period)

    def out(self) -> Bag:
        return {"tick": [self.ticks]}


class Sink(Atomic):
    def __init__(self, name="sink"):
        super().__init__(name)
        self.add_inport("in")
        self.seen = []

    def initialize(self):
        self.seen = []
        self.passivate()

    def deltext(self, e, x):
        self.seen.extend(x.get("in", ()))


class Burst(Atomic):
    """Takes `n` zero-time steps, then passivates; `n=None` never stops."""

    def __init__(self, n):
        super().__init__("burst")
        self.n = n

    def initialize(self):
        self.k = 0
        self.hold_in("active", 1.0)

    def deltint(self):
        self.k += 1
        if self.n is not None and self.k >= self.n:
            self.passivate()
        else:
            self.hold_in("active", 0.0)


def _pair(src_port="tick", dst_port="in"):
    g = Digraph("g")
    src, snk = Ticker(), Sink()
    g.add(src)
    g.add(snk)
    g.add_coupling(src, src_port, snk, dst_port)
    return g, src, snk


# --- structure validation ---------------------------------------------------
def test_duplicate_component_names_are_rejected():
    g = Digraph("g")
    g.add(Sink("x"))
    g.add(Sink("x"))
    with pytest.raises(ModelStructureError, match="duplicate component name 'x'"):
        TimeCoordinator(g)


def test_component_named_like_its_digraph_is_rejected():
    g = Digraph("g")
    g.add(Sink("g"))
    with pytest.raises(ModelStructureError, match="duplicate"):
        TimeCoordinator(g)


def test_coupling_to_unknown_component_is_rejected():
    g = Digraph("g")
    src = Ticker()
    g.add(src)
    g.add_coupling(src, "tick", Sink("ghost"), "in")
    with pytest.raises(ModelStructureError, match="unknown component 'ghost'"):
        TimeCoordinator(g)


def test_undeclared_ports_are_rejected():
    with pytest.raises(ModelStructureError, match="no output port 'tock'"):
        TimeCoordinator(_pair(src_port="tock")[0])
    with pytest.raises(ModelStructureError, match="no input port 'inn'"):
        TimeCoordinator(_pair(dst_port="inn")[0])


def test_undeclared_digraph_ports_are_rejected():
    g = Digraph("g")
    snk = Sink()
    g.add(snk)
    g.add_coupling(g, "in", snk, "in")  # g never declared "in"
    with pytest.raises(ModelStructureError, match="'g' has no input port 'in'"):
        TimeCoordinator(g)


def test_atomic_coupled_to_itself_is_rejected():
    class Echo(Atomic):
        def __init__(self):
            super().__init__("echo")
            self.add_inport("in")
            self.add_outport("out")

    g = Digraph("g")
    echo = Echo()
    g.add(echo)
    g.add_coupling(echo, "out", echo, "in")
    with pytest.raises(ModelStructureError, match="coupled to itself"):
        TimeCoordinator(g)


def test_self_loop_through_the_hierarchy_is_rejected():
    class Echo(Atomic):
        def __init__(self):
            super().__init__("echo")
            self.add_inport("in")
            self.add_outport("out")

    inner = Digraph("inner")
    inner.add_inport("in")
    inner.add_outport("out")
    echo = Echo()
    inner.add(echo)
    inner.add_coupling(inner, "in", echo, "in")
    inner.add_coupling(echo, "out", inner, "out")
    top = Digraph("top")
    top.add(inner)
    top.add_coupling(inner, "out", inner, "in")
    with pytest.raises(ModelStructureError, match="coupled to itself"):
        TimeCoordinator(top)


# --- zero-time loop guard ----------------------------------------------------
def test_zero_time_loop_raises_in_a_coordinator():
    g = Digraph("g")
    g.add(Burst(None))
    coord = TimeCoordinator(g)
    coord.max_rounds_per_instant = 50
    with pytest.raises(ZeroTimeLoopError, match="more than 50 rounds at time 1.0"):
        coord.simulate(10.0)


def test_zero_time_loop_raises_in_an_atomic_simulator():
    sim = TimeAtomicSimulator(Burst(None))
    sim.max_rounds_per_instant = 50
    with pytest.raises(ZeroTimeLoopError):
        sim.simulate(10.0)


def test_finite_zero_time_burst_within_the_limit_runs():
    g = Digraph("g")
    burst = Burst(40)
    g.add(burst)
    coord = TimeCoordinator(g)
    coord.max_rounds_per_instant = 40
    coord.simulate(10.0)
    assert burst.k == 40
    coord.max_rounds_per_instant = 39
    coord.initialize(0.0)
    with pytest.raises(ZeroTimeLoopError):
        coord.simulate(10.0)


# --- initialization -----------------------------------------------------------
def test_facade_digraph_initializes_once_with_or_without_reset():
    g, src, snk = _pair()
    f = DevsSuiteFacade(g)
    assert src.inits == 0
    f.simulate_to_time(3.0)  # no reset(): the first run initializes
    assert src.inits == 1 and snk.seen == [0, 1, 2]

    g, src, snk = _pair()
    f = DevsSuiteFacade(g)
    f.reset()
    f.simulate_to_time(3.0)
    assert src.inits == 1 and snk.seen == [0, 1, 2]


def test_atomic_simulate_to_time_gates_on_time_not_iterations():
    t = Ticker(period=0.5)
    f = DevsSuiteFacade(t)
    f.simulate_to_time(2.0)
    assert t.ticks == 4  # events at 0.5, 1.0, 1.5, 2.0
    f.simulate_iterations(3)
    assert t.ticks == 7


# --- injection ------------------------------------------------------------------
def test_coordinator_injection_out_of_range_or_undeclared_port_raises():
    g = Digraph("g")
    g.add_inport("in")
    snk = Sink()
    g.add(snk)
    g.add(Ticker())  # next event at 1.0
    g.add_coupling(g, "in", snk, "in")
    f = DevsSuiteFacade(g)
    f.reset()
    sim = f.get_simulator()
    with pytest.raises(ValueError, match="elapsed time 1.5"):
        sim.sim_inject(1.5, "in", "late")
    with pytest.raises(ValueError, match="elapsed time -1"):
        sim.sim_inject(-1, "in", "early")
    with pytest.raises(ValueError, match="no input port 'nope'"):
        sim.sim_inject(0.5, "nope", 1)
    sim.sim_inject(1.0, "in", "ok")
    assert snk.seen == ["ok"]


def test_atomic_injection_out_of_range_or_undeclared_port_raises():
    sim = TimeAtomicSimulator(Sink())
    sim.initialize(0.0)
    with pytest.raises(ValueError, match="no input port 'nope'"):
        sim.sim_inject(1.0, "nope", 1)
    sim.sim_inject(1.0, "in", "a")
    assert sim.get_model().seen == ["a"]

    sim = TimeAtomicSimulator(Ticker())
    sim.initialize(0.0)
    with pytest.raises(ValueError, match="elapsed time 2"):
        sim.sim_inject(2, {"tick": [1]})


# --- default confluent transition ------------------------------------------------
def test_default_deltcon_passes_zero_elapsed_time_to_deltext():
    class Probe(Ticker):
        def __init__(self):
            super().__init__("probe")
            self.add_inport("in")
            self.elapsed = []

        def deltext(self, e, x):
            self.elapsed.append(e)

    g = Digraph("g")
    src, probe = Ticker("src"), Probe()
    g.add(src)
    g.add(probe)
    g.add_coupling(src, "tick", probe, "in")
    f = DevsSuiteFacade(g)
    f.simulate_to_time(2.0)
    # Both tick at 1.0 and 2.0: every input is confluent with the probe's own event.
    assert probe.elapsed == [0.0, 0.0]


# --- exact time -------------------------------------------------------------------
def test_fraction_time_keeps_simultaneous_events_simultaneous():
    from fractions import Fraction

    class Every(Atomic):
        def __init__(self, name, step):
            super().__init__(name)
            self.add_outport("out")
            self.step = step

        def initialize(self):
            self.hold_in("active", self.step)

        def deltint(self):
            self.hold_in("active", self.step)

        def out(self):
            return {"out": [self.get_name()]}

    def run(tenth, three_tenths):
        g = Digraph("g")
        g.add_outport("out")
        for m in (Every("fast", tenth), Every("slow", three_tenths)):
            g.add(m)
            g.add_coupling(m, "out", g, "out")
        return DevsSuiteFacade(g).advance(three_tenths + tenth / 2)

    # Floats: 0.1 + 0.1 + 0.1 != 0.3, so "fast" and "slow" fire in separate rounds.
    assert len(run(0.1, 0.3)) == 4
    # Fractions: exactly simultaneous, one round with both outputs.
    out = run(Fraction(1, 10), Fraction(3, 10))
    assert len(out) == 3
    assert out[-1] == (Fraction(3, 10), {"out": ["fast", "slow"]})
