from devspy import Atomic, Bag
from devspy.simulation.atomic_simulator import AtomicSimulator


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


def test_iteration_limited_simulation_runs_exact_count():
    t = Ticker()
    sim = AtomicSimulator(t)
    sim.initialize(0.0)
    sim.simulate(4)
    assert t.ticks == 4
