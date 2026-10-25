import math

from devspy import Atomic, Bag


class Ticker(Atomic):
    def __init__(self) -> None:
        super().__init__("ticker")
        self.add_outport("tick")
        self.ticks = 0

    def initialize(self) -> None:
        self.ticks = 0
        self.hold_in("active", 1.0)

    def deltint(self) -> None:
        self.ticks += 1
        self.hold_in("active", 1.0)

    def out(self) -> Bag:
        return {"tick": [self.ticks + 1]}


def test_initial_state_is_passive():
    a = Atomic("a")
    assert a.phase == "passive"
    assert a.sigma == math.inf
    assert a.ta() == math.inf


def test_hold_in_and_passivate():
    a = Atomic("a")
    a.hold_in("busy", 2.5)
    assert a.phase_is("busy")
    assert a.get_sigma() == 2.5
    a.passivate()
    assert a.phase_is("passive")
    assert a.get_sigma() == math.inf


def test_continue_decrements_sigma():
    a = Atomic("a")
    a.hold_in("active", 5.0)
    a.cont(1.5)
    assert a.get_sigma() == 3.5


def test_ticker_initialize_then_out():
    t = Ticker()
    t.initialize()
    assert t.ta() == 1.0
    assert t.out() == {"tick": [1]}
