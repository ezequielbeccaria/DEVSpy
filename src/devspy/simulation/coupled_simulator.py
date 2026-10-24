from __future__ import annotations

from typing import Optional

from devspy.modeling.devs import IOBasicDevs
from devspy.simulation.atomic_simulator import AtomicSimulator

# A resolved coupling destination: (target simulator, input port), or
# (None, output port) for an output port of the root digraph.
Route = tuple[Optional["CoupledSimulator"], str]
# Routes grouped by destination port: (port, [targets]).
Fanout = tuple[str, list[Optional["CoupledSimulator"]]]


class CoupledSimulator(AtomicSimulator):
    """Simulator of one atomic model inside a (flattened) `Coordinator`.

    Holds the model's state times, its input bag and its routes: for each output
    port, the atomic input ports it reaches through the coupling hierarchy.
    The coordinator drives it directly; it has no simulation loop of its own.
    """

    __slots__ = ("index", "routes", "fanout", "version", "ta_is_sigma")

    def __init__(self, model: IOBasicDevs, index: int = 0) -> None:
        super().__init__(model)
        from devspy.modeling.atomic import Atomic

        self.index = index
        self.routes: dict[str, list[Route]] = {}
        self.fanout: dict[str, list[Fanout]] = {}
        # Bumped on every reschedule; invalidates stale heap entries.
        self.version = 0
        # ta() is Atomic's (return sigma): the coordinator reads sigma directly.
        self.ta_is_sigma: bool = type(model).ta is Atomic.ta
        model.set_simulator(self)
