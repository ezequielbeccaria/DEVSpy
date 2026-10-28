"""Adding and removing models and couplings while the simulation runs."""

import pytest

from devspy import Atomic, SimulationManager, Digraph, ModelStructureError


class Pulse(Atomic):
    def __init__(self, name, period=1.0):
        super().__init__(name)
        self.add_outport("out")
        self.period = period

    def initialize(self):
        self.k = 0
        self.hold_in("active", self.period)

    def deltint(self):
        self.k += 1
        self.hold_in("active", self.period)

    def out(self):
        return {"out": [self.k]}


class Sink(Atomic):
    def __init__(self, name):
        super().__init__(name)
        self.add_inport("in")
        self.seen = []
        self.born = None

    def initialize(self):
        sim = self.get_simulator()
        self.born = sim.t_l if sim is not None else None
        self.seen = []
        self.passivate()

    def deltext(self, e, x):
        self.seen.extend((self.get_simulator().t_l + e, v) for v in x["in"])


class Factory(Pulse):
    """At t=2 adds a sink coupled to its own output; at t=4 removes it."""

    def deltint(self):
        super().deltint()
        if self.k == 2:
            self.sink = Sink("late")
            self.add_model(self.sink)
            self.add_coupling(self, "out", self.sink, "in")
        elif self.k == 4:
            self.remove_model("late")


def _net(*models):
    g = Digraph("g")
    for m in models:
        g.add(m)
    return g


def test_model_added_during_a_transition_starts_after_the_round():
    factory = Factory("factory")
    f = SimulationManager(_net(factory))
    f.advance(10.0)
    sink = factory.sink
    # Added in the δ of t=2: it was not there for the output at t=2, starts at 2,
    # receives the outputs of t=3 and t=4, and is gone afterwards.
    assert sink.born == 2.0
    assert sink.seen == [(3.0, 2), (4.0, 3)]
    assert "late" not in [s.get_model().get_name() for s in f.get_simulator().simulators]
    assert factory.get_parent().get_couprel().translate("factory", "out") == set()


def test_removed_model_leaves_the_schedule():
    a, b = Pulse("a"), Pulse("b", period=0.5)
    g = _net(a, b)
    f = SimulationManager(g)
    f.advance(1.0)
    g.remove(b)  # outside a round: applied immediately
    f.advance(5.0)
    assert b.k == 2  # stopped at t=1
    assert a.k == 5


def test_model_added_between_runs_starts_at_the_current_time():
    a = Pulse("a")
    g = _net(a)
    f = SimulationManager(g)
    f.advance(2.5)
    assert f.time == 2.0  # the clock is at the last event
    late = Pulse("late")
    g.add(late)
    f.advance(5.0)
    assert late.k == 3  # started at 2.0: events at 3, 4 and 5


def test_rejected_change_outside_a_round_is_undone():
    a, s = Pulse("a"), Sink("s")
    g = _net(a, s)
    f = SimulationManager(g)
    f.advance(1.0)
    with pytest.raises(ModelStructureError, match="no input port 'nope'"):
        g.add_coupling(a, "out", s, "nope")
    assert g.get_couprel().translate("a", "out") == set()
    with pytest.raises(ModelStructureError, match="duplicate"):
        g.add(Pulse("a"))
    assert len(g.get_components()) == 2
    f.advance(3.0)  # still usable
    assert a.k == 3


def test_invalid_change_inside_a_round_raises_at_the_end_of_it():
    class Bad(Pulse):
        def deltint(self):
            super().deltint()
            self.add_coupling(self, "out", self, "out")  # an output is no input

    f = SimulationManager(_net(Bad("bad")))
    with pytest.raises(ModelStructureError):
        f.advance(5.0)


def test_editing_before_reset_is_fine():
    a = Pulse("a")
    g = Digraph("g")
    g.add(a)
    f = SimulationManager(g)
    s = Sink("s")
    g.add(s)
    g.add_coupling(a, "out", s, "in")
    f.reset()
    f.advance(2.0)
    assert s.seen == [(1.0, 0), (2.0, 1)]


def test_snapshot_refuses_a_different_structure():
    a = Pulse("a")
    g = _net(a)
    f = SimulationManager(g)
    f.advance(1.0)
    snap = f.snapshot()
    g.add(Pulse("b"))
    with pytest.raises(ValueError, match="structure changed"):
        f.restore(snap)


def test_structure_changes_inside_nested_digraphs():
    inner = Digraph("inner")
    inner.add_outport("out")
    factory = Factory("factory")
    inner.add(factory)
    top = Digraph("top")
    top.add(inner)
    f = SimulationManager(top)
    f.advance(10.0)
    assert factory.sink.seen == [(3.0, 2), (4.0, 3)]
