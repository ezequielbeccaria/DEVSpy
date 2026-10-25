"""Stepping (advance/inject), observers and snapshot/restore on the facade."""

import random

import pytest

from devspy import Atomic, DevsSuiteFacade, Digraph, Observer


class Echo(Atomic):
    """Replies to every input with value * 10 after `delay`."""

    def __init__(self, name="echo", delay=1.0):
        super().__init__(name)
        self.add_inport("in")
        self.add_outport("out")
        self.delay = delay

    def initialize(self):
        self.pending = []
        self.passivate()

    def deltext(self, e, x):
        self.pending.extend(v * 10 for v in x.get("in", ()))
        self.hold_in("busy", self.delay)

    def deltint(self):
        self.pending = []
        self.passivate()

    def out(self):
        return {"out": list(self.pending)}


class Clock(Atomic):
    def __init__(self, name="clock", period=1.0):
        super().__init__(name)
        self.add_outport("tick")
        self.period = period

    def initialize(self):
        self.n = 0
        self.rng = random.Random(42)
        self.hold_in("active", self.period)

    def deltint(self):
        self.n += 1
        self.hold_in("active", self.period)

    def out(self):
        return {"tick": [self.n]}


def _echo_net():
    g = Digraph("net")
    g.add_inport("in")
    g.add_outport("out")
    echo = Echo()
    g.add(echo)
    g.add_coupling(g, "in", echo, "in")
    g.add_coupling(echo, "out", g, "out")
    return g, echo


def _clock_net():
    g = Digraph("net")
    g.add_outport("tick")
    clock = Clock()
    g.add(clock)
    g.add_coupling(clock, "tick", g, "tick")
    return g, clock


def test_advance_returns_root_outputs_instead_of_printing(capsys):
    g, _ = _clock_net()
    f = DevsSuiteFacade(g)
    assert f.advance(3.0) == [(1.0, {"tick": [0]}), (2.0, {"tick": [1]}), (3.0, {"tick": [2]})]
    assert f.time == 3.0 and f.next_event_time == 4.0
    assert capsys.readouterr().out == ""


def test_advance_can_stop_at_the_first_output():
    g, _ = _clock_net()
    f = DevsSuiteFacade(g)
    assert f.advance(stop_on_output=True) == [(1.0, {"tick": [0]})]
    assert f.advance(stop_on_output=True) == [(2.0, {"tick": [1]})]


def test_gym_style_loop():
    g, _ = _echo_net()
    f = DevsSuiteFacade(g)
    f.reset()
    assert f.inject("in", 1, at=0.5) == []
    assert f.advance(stop_on_output=True) == [(1.5, {"out": [10]})]
    # Inject at the current time (e = 0), then run to the reply.
    assert f.inject("in", 2) == []
    assert f.time == 1.5
    assert f.advance(stop_on_output=True) == [(2.5, {"out": [20]})]


def test_inject_returns_outputs_of_the_rounds_it_runs_first():
    g, _ = _echo_net()
    f = DevsSuiteFacade(g)
    f.inject("in", 1, at=1.0)
    # The reply at 2.0 happens before the injection at 3.0, and is returned.
    assert f.inject({"in": [5, 6]}, at=3.0) == [(2.0, {"out": [10]})]
    assert f.advance() == [(4.0, {"out": [50, 60]})]


def test_inject_at_an_event_time_is_confluent():
    g, _ = _echo_net()
    f = DevsSuiteFacade(g)
    f.inject("in", 1, at=1.0)
    # The echo is due at 2.0: λ first (reply 10), then δcon with the new input.
    assert f.inject("in", 2, at=2.0) == [(2.0, {"out": [10]})]
    assert f.advance() == [(3.0, {"out": [20]})]


def test_inject_into_the_past_or_on_an_unknown_port_raises():
    g, _ = _echo_net()
    f = DevsSuiteFacade(g)
    f.inject("in", 1, at=2.0)
    with pytest.raises(ValueError, match="already at 2.0"):
        f.inject("in", 1, at=1.0)
    with pytest.raises(ValueError, match="no input port 'nope'"):
        f.inject("nope", 1)


def test_inject_far_ahead_does_not_drift():
    g, echo = _echo_net()
    echo.delay = 0.1
    f = DevsSuiteFacade(g)
    t = 0.0
    for _ in range(50):
        t += 0.3
        f.inject("in", 1, at=t)
        assert f.time == t


def test_atomic_facade_supports_the_same_api():
    f = DevsSuiteFacade(Echo())
    assert f.inject("in", 3, at=1.0) == []
    assert f.advance() == [(2.0, {"out": [30]})]
    snap = f.snapshot()
    f.inject("in", 4, at=5.0)
    assert f.advance() == [(6.0, {"out": [40]})]
    f.restore(snap)
    assert f.time == 2.0
    f.inject("in", 4, at=5.0)
    assert f.advance() == [(6.0, {"out": [40]})]


def test_observer_receives_outputs_and_transitions():
    class Rec(Observer):
        def __init__(self):
            self.events = []

        def on_output(self, t, model, y):
            self.events.append((t, model.get_name(), "out", y))

        def on_transition(self, t, model, kind, e, x):
            self.events.append((t, model.get_name(), kind, e, x))

    g, _ = _echo_net()
    f = DevsSuiteFacade(g)
    rec = Rec()
    f.add_observer(rec)
    f.inject("in", 1, at=0.5)
    f.advance()
    assert rec.events == [
        (0.5, "echo", "ext", 0.5, {"in": [1]}),
        (1.5, "echo", "out", {"out": [10]}),
        (1.5, "echo", "int", 1.0, {}),
    ]
    f.remove_observer(rec)
    f.inject("in", 2)
    f.advance()
    assert len(rec.events) == 3


def test_snapshot_restores_in_place_and_repeatably():
    g, clock = _clock_net()
    f = DevsSuiteFacade(g)
    f.advance(2.0)
    clock.rng.random()
    snap = f.snapshot()
    expected_draw = clock.rng.random()
    first = f.advance(5.0)
    clock.extra = "added later"
    for _ in range(2):
        f.restore(snap)
        assert f.time == 2.0 and clock.n == 2
        assert not hasattr(clock, "extra")  # attributes added after the snapshot go
        assert clock.rng.random() == expected_draw  # RNG state restored
        assert f.advance(5.0) == first
    # The model object is the same one the user holds.
    assert f.get_simulator().simulators[0].get_model() is clock


def test_snapshot_keeps_references_between_models():
    class Peer(Clock):
        pass

    g = Digraph("net")
    a, b = Clock("a"), Peer("b")
    g.add(a)
    g.add(b)
    b.partner = a  # model-to-model reference: must stay a reference
    f = DevsSuiteFacade(g)
    f.advance(1.0)
    snap = f.snapshot()
    f.advance(3.0)
    f.restore(snap)
    assert b.partner is a
    assert a.n == 1
