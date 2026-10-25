from __future__ import annotations

import copy
from typing import Optional, Union

from devspy.exceptions import NoModelSetError
from devspy.modeling.atomic import Atomic
from devspy.modeling.digraph import Digraph
from devspy.simulation.time_atomic_simulator import TimeAtomicSimulator
from devspy.simulation.time_coordinator import TimeCoordinator


class DevsSuiteFacade:
    """Started as a port of DEVSJAVA's `facade.DevsSuiteFacade`.

    Entry point for headless DEVS simulation. Accepts an atomic or digraph
    model (or a preconfigured `TimeCoordinator`), and exposes iteration- and
    time-limited simulation methods.
    """

    def __init__(
        self,
        model: Optional[Union[Atomic, Digraph, TimeCoordinator]] = None,
    ) -> None:
        self._simulation_done: bool = False
        self._atomic_simulator: Optional[TimeAtomicSimulator] = None
        self._coordinator: Optional[TimeCoordinator] = None

        if model is None:
            return
        if isinstance(model, Atomic):
            self.set_atomic_model(model)
        elif isinstance(model, Digraph):
            # Not initialized here: the first reset() or simulate_*() call does it,
            # so the usual "construct, reset(), simulate" initializes exactly once.
            self.set_digraph_model(model, initialize=False)
        elif isinstance(model, TimeCoordinator):
            self._coordinator = model
        else:
            raise TypeError(f"Unsupported model type: {type(model)!r}")

    # --- setters -----------------------------------------------------------
    def set_atomic_model(self, model: Atomic) -> None:
        self._coordinator = None
        self._atomic_simulator = TimeAtomicSimulator(model)
        self._atomic_simulator.initialize(0.0)

    def set_digraph_model(self, model: Digraph, initialize: bool = True) -> None:
        self._atomic_simulator = None
        self._coordinator = TimeCoordinator(model, set_simulators=True)
        if initialize:
            self._coordinator.initialize(0.0)

    # --- running -----------------------------------------------------------
    def simulate_iterations(self, iterations: int) -> None:
        self._simulation_done = False
        sim = self._require_sim()
        # Use the base-class iteration-count simulate.
        if self._atomic_simulator is not None:
            from devspy.simulation.atomic_simulator import AtomicSimulator
            AtomicSimulator.simulate(self._atomic_simulator, iterations)
        else:
            from devspy.simulation.coordinator import Coordinator
            Coordinator.simulate(self._coordinator, iterations)  # type: ignore[arg-type]
        self._simulation_done = True
        _ = sim  # retained for clarity

    def simulate_to_time(self, time_or_init: float, end_time: Optional[float] = None) -> None:
        self._simulation_done = False
        self._require_sim()
        if end_time is None:
            max_t = float(time_or_init)
            if self._atomic_simulator is not None:
                self._atomic_simulator.simulate(max_t)
            else:
                assert self._coordinator is not None
                self._coordinator.simulate(max_t)
        else:
            init_t = float(time_or_init)
            max_t = float(end_time)
            if self._atomic_simulator is not None:
                self._atomic_simulator.simulate_from_to(init_t, max_t)
            else:
                assert self._coordinator is not None
                self._coordinator.simulate_from_to(init_t, max_t)
        self._simulation_done = True

    def reset(self) -> None:
        self._require_sim()
        if self._atomic_simulator is not None:
            self._atomic_simulator.initialize(0.0)
        else:
            assert self._coordinator is not None
            self._coordinator.initialize(0.0)

    def deep_cloning(self) -> Union[TimeAtomicSimulator, TimeCoordinator]:
        sim = self._require_sim()
        return copy.deepcopy(sim)

    # --- introspection -----------------------------------------------------
    def is_simulation_done(self) -> bool:
        return self._simulation_done

    def get_simulator(self) -> Union[TimeAtomicSimulator, TimeCoordinator]:
        return self._require_sim()

    # --- helpers -----------------------------------------------------------
    def _require_sim(self) -> Union[TimeAtomicSimulator, TimeCoordinator]:
        if self._atomic_simulator is None and self._coordinator is None:
            raise NoModelSetError("No model to start simulation set.")
        return self._atomic_simulator or self._coordinator  # type: ignore[return-value]
