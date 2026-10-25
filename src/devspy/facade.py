from __future__ import annotations

import copy
import math
from typing import Any, Optional, Union

from devspy.exceptions import NoModelSetError
from devspy.modeling.atomic import Atomic
from devspy.modeling.devs import Bag
from devspy.modeling.digraph import Digraph
from devspy.simulation.observer import Observer
from devspy.simulation.real_time import RealTimeRunner, WallClock
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

    # --- stepping ----------------------------------------------------------
    @property
    def time(self) -> float:
        """Time of the last event (or injection)."""
        return self._require_sim().t_l

    @property
    def next_event_time(self) -> float:
        """Time of the next internal event (`inf` if every model is passive)."""
        return self._require_sim().next_tn()

    def advance(
        self, until: float = math.inf, stop_on_output: bool = False
    ) -> list[tuple[float, Bag]]:
        """Run every round with `t_n <= until` and return the root outputs as
        `(t, bag)` pairs, instead of printing them. With `stop_on_output=True`
        it returns after the first round that produces root output."""
        sim = self._require_sim()
        return self._collect(sim, stop_on_output, lambda: sim._run(math.inf, until))

    def inject(
        self, port_or_bag: Union[str, Bag], value: Any = None, at: Optional[float] = None
    ) -> list[tuple[float, Bag]]:
        """Inject external input `at` an absolute time (default: `self.time`).

        Rounds strictly before `at` run first; their root outputs, and those of
        the injected round, are returned as `(t, bag)` pairs. If `at` is also the
        time of an internal event, both are one confluent round. Raises
        `ValueError` if `at` is before `self.time` or a port is undeclared.
        """
        sim = self._require_sim()
        if not sim.initialized:
            sim.initialize(0.0)
        t = sim.t_l if at is None else float(at)
        if t < sim.t_l:
            raise ValueError(f"cannot inject at {t}: the simulation is already at {sim.t_l}")
        bag = port_or_bag if isinstance(port_or_bag, dict) else {str(port_or_bag): [value]}

        def run() -> None:
            sim._run(math.inf, math.nextafter(t, -math.inf))  # rounds strictly before t
            sim.inject_at(t, bag)

        return self._collect(sim, False, run)

    def add_observer(self, observer: Observer) -> None:
        """Notify `observer` of every λ output and δ transition from now on."""
        self._require_sim().observers.append(observer)

    def remove_observer(self, observer: Observer) -> None:
        self._require_sim().observers.remove(observer)

    def real_time(self, speed: float = 1.0, clock: Optional[WallClock] = None) -> RealTimeRunner:
        """A runner that paces the simulation against the wall clock (`speed`
        simulated units per second). Call `run(until)` in one thread and
        `post(...)`/`stop()` from any other."""
        return RealTimeRunner(self._require_sim(), speed=speed, clock=clock)

    # --- snapshots ---------------------------------------------------------
    def snapshot(self) -> dict:
        """Copy of the whole simulation state, for `restore`. Model objects stay
        the same; anything else they reference (RNGs, buffers...) is copied."""
        return self._require_sim().snapshot()

    def restore(self, snapshot: dict) -> None:
        """Put the simulation back in the state of `snapshot`, in place."""
        self._require_sim().restore(snapshot)

    def deep_cloning(self) -> Union[TimeAtomicSimulator, TimeCoordinator]:
        sim = self._require_sim()
        return copy.deepcopy(sim)

    # --- introspection -----------------------------------------------------
    def is_simulation_done(self) -> bool:
        return self._simulation_done

    def get_simulator(self) -> Union[TimeAtomicSimulator, TimeCoordinator]:
        return self._require_sim()

    # --- helpers -----------------------------------------------------------
    @staticmethod
    def _collect(sim, stop_on_output: bool, run) -> list[tuple[float, Bag]]:
        """Run `run()` with the simulator's root outputs collected, not printed."""
        sink: list[tuple[float, Bag]] = []
        saved = sim._sink, sim._stop_on_output
        sim._sink, sim._stop_on_output = sink, stop_on_output
        try:
            run()
        finally:
            sim._sink, sim._stop_on_output = saved
        return sink

    def _require_sim(self) -> Union[TimeAtomicSimulator, TimeCoordinator]:
        if self._atomic_simulator is None and self._coordinator is None:
            raise NoModelSetError("No model to start simulation set.")
        return self._atomic_simulator or self._coordinator  # type: ignore[return-value]
