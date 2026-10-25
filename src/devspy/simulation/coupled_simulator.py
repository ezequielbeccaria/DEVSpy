from __future__ import annotations

from typing import Optional

from devspy.modeling.content import Content
from devspy.modeling.devs import IOBasicDevs
from devspy.simulation.atomic_simulator import AtomicSimulator

# A resolved coupling destination: (target simulator, input port), or
# (None, output port) for an output port of the root digraph.
Route = tuple[Optional["CoupledSimulator"], str]
# Routes grouped by destination port: (port, [targets]).
Fanout = tuple[str, list[Optional["CoupledSimulator"]]]


class CoupledSimulator(AtomicSimulator):
    """Simulator of one atomic model inside a (flattened) `Coordinator`.

    Holds the model's state times, its input bag and `routes`: for each output
    port, the atomic input ports it reaches through the coupling hierarchy.
    The coordinator drives it directly; it has no simulation loop of its own.
    """

    def __init__(self, model: IOBasicDevs, index: int = 0) -> None:
        super().__init__(model)
        self.index = index
        self.routes: dict[str, list[Route]] = {}
        self.fanout: dict[str, list[Fanout]] = {}
        # Bumped on every reschedule; invalidates stale heap entries.
        self.version = 0
        model.set_simulator(self)

    def put_messages(self, c: Content) -> None:
        self.input.add(c)
