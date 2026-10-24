import pytest

from devspy import (
    Atomic,
    Bag,
    DevsSuiteFacade,
    Digraph,
    NoModelSetError,
)


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


class Sink(Atomic):
    def __init__(self) -> None:
        super().__init__("sink")
        self.add_inport("in")
        self.seen: list[int] = []

    def initialize(self) -> None:
        self.seen = []
        self.passivate()

    def deltext(self, e: float, x: Bag) -> None:
        self.seen.extend(x.get("in", ()))


def test_facade_without_model_raises():
    facade = DevsSuiteFacade()
    with pytest.raises(NoModelSetError):
        facade.simulate_iterations(1)
    with pytest.raises(NoModelSetError):
        facade.reset()


def test_facade_atomic_simulate_to_time():
    t = Ticker()
    facade = DevsSuiteFacade(t)
    facade.reset()
    facade.simulate_to_time(5.0)
    assert facade.is_simulation_done()
    assert t.ticks == 5


def test_facade_digraph_simulate_to_time():
    g = Digraph("g")
    src = Ticker()
    snk = Sink()
    g.add(src)
    g.add(snk)
    g.add_coupling(src, "tick", snk, "in")
    facade = DevsSuiteFacade(g)
    facade.reset()
    facade.simulate_to_time(3.0)
    assert len(snk.seen) == 3


def test_facade_simulate_iterations_on_atomic():
    t = Ticker()
    facade = DevsSuiteFacade(t)
    facade.reset()
    facade.simulate_iterations(4)
    assert t.ticks == 4


def test_facade_simulate_to_time_with_init_and_end():
    t = Ticker()
    facade = DevsSuiteFacade(t)
    facade.reset()
    facade.simulate_to_time(0.0, 3.0)
    assert t.ticks == 3


def test_facade_deep_cloning_is_independent():
    t = Ticker()
    facade = DevsSuiteFacade(t)
    facade.reset()
    facade.simulate_to_time(2.0)

    snapshot = facade.deep_cloning()
    # Advance the live facade; the snapshot must remain frozen.
    facade.simulate_to_time(0.0, 5.0)

    from devspy.simulation.time_atomic_simulator import TimeAtomicSimulator
    assert isinstance(snapshot, TimeAtomicSimulator)
    assert snapshot.get_model() is not t
    assert snapshot.get_model().ticks == 2
    assert t.ticks == 5
