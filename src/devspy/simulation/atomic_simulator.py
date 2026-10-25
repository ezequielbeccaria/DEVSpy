from __future__ import annotations

import math
from typing import Any, Optional

from devspy.exceptions import ZeroTimeLoopError
from devspy.modeling.devs import Bag, IOBasicDevs
from devspy.simulation.observer import (
    Observer,
    deepcopy_keeping,
    model_state,
    set_model_state,
)
from devspy.util.logging import FULL, is_enabled, log

INFINITY = math.inf


class AtomicSimulator:
    """Drives a single atomic model through the DEVS state-transition protocol.

    The run loops initialize the model first if `initialize()` was never called,
    and raise `ZeroTimeLoopError` after `max_rounds_per_instant` consecutive
    rounds at the same time (`None` disables the check).
    """

    max_rounds_per_instant: Optional[int] = 100_000

    __slots__ = ("my_model", "t_l", "t_n", "input", "output", "custom_show_state", "__dict__")

    def __init__(self, model: Any = None) -> None:
        # Any, not IOBasicDevs: Coordinator passes its Digraph here.
        self.my_model: Any = model
        # Times start as the int 0 so that int or Fraction time advances stay exact.
        self.t_l: float = 0
        self.t_n: float = 0
        self.input: Bag = {}
        self.output: Bag = {}
        self.initialized: bool = False
        self.observers: list[Observer] = []
        # Root outputs go to _sink as (t, bag) when it is a list, else are printed.
        self._sink: Optional[list[tuple[float, Bag]]] = None
        self._stop_on_output = False
        self._stop_sim_flag = False
        self._out_t: float = 0
        # The default Atomic.show_state only logs; skip calling it when logging is off.
        self.custom_show_state: bool = _has_custom_show_state(model)

    # --- time accessors ----------------------------------------------------
    def next_tn(self) -> float:
        return self.t_n

    def get_model(self) -> Optional[IOBasicDevs]:
        return self.my_model

    # --- lifecycle ---------------------------------------------------------
    def initialize(self, current_time: float = 0) -> None:
        assert self.my_model is not None
        self.my_model.initialize()
        self.t_l = current_time
        self.t_n = self.t_l + self.my_model.ta()
        self.initialized = True
        log(f"INITIALIZATION, time: {self.t_l}, next event at: {self.t_n}", FULL)
        self.my_model.show_state()

    # --- transition primitives --------------------------------------------
    def delt_func(self, t: float) -> None:
        self.wrap_deltfunc(t, {})

    def wrap_deltfunc(self, t: float, x: Optional[Bag] = None) -> None:
        """The DEVS state-transition dispatch: deltint, deltext or deltcon."""
        assert self.my_model is not None
        if x is None:
            x = self.input
            self.input = {}
        if not x and t != self.t_n:
            return
        if x and t == self.t_n:
            kind = "con"
            self.my_model.deltcon(t - self.t_l, x)
        elif t == self.t_n:
            kind = "int"
            self.my_model.deltint()
        else:
            kind = "ext"
            self.my_model.deltext(t - self.t_l, x)
        for obs in self.observers:
            obs.on_transition(t, self.my_model, kind, t - self.t_l, x)
        self.t_l = t
        self.t_n = self.t_l + self.my_model.ta()

    def compute_input_output(self, t: float) -> None:
        assert self.my_model is not None
        self.output = (self.my_model.out() or {}) if t == self.t_n else {}
        self._out_t = t
        if self.output:
            for obs in self.observers:
                obs.on_output(t, self.my_model, self.output)

    # --- show/print --------------------------------------------------------
    def show_model_state(self) -> None:
        assert self.my_model is not None
        if self.custom_show_state or is_enabled(FULL):
            self.my_model.show_state()

    def show_output(self) -> None:
        if not self.output:
            return
        if self._sink is None:
            print(_format_bag(self.output))
        else:
            self._sink.append((self._out_t, self.output))
            if self._stop_on_output:
                self._stop_sim_flag = True

    # --- simulation loops --------------------------------------------------
    def simulate(self, num_iter: float) -> None:
        """Run at most `num_iter` iterations (transitions)."""
        self._run(num_iter, INFINITY)

    def _run(self, num_iter: float, max_time: float) -> None:
        """Run while `t_n <= max_time`, for at most `num_iter` iterations."""
        if not self.initialized:
            self.initialize(0)
        self._stop_sim_flag = False
        i = 1
        guard = _InstantGuard(self.max_rounds_per_instant)
        while (
            self.t_n < INFINITY
            and self.t_n <= max_time
            and i <= num_iter
            and not self._stop_sim_flag
        ):
            if is_enabled(FULL):
                log(f"ITERATION {i} ,time: {self.t_n}", FULL)
            guard.check(self.t_n)
            self.compute_input_output(self.t_n)
            self.show_output()
            self.delt_func(self.t_n)
            self.show_model_state()
            i += 1
        log(f"Terminated Normally at ITERATION {i} ,time: {self.t_n}", FULL)

    def stop_simulation(self) -> None:
        """Make the running loop return after the current round."""
        self._stop_sim_flag = True

    # --- snapshots ---------------------------------------------------------
    def snapshot(self) -> dict:
        """Copy of the simulation state (the model's attributes and the times),
        for `restore`. The model object itself is not copied."""
        state = {"model": model_state(self.my_model), "times": (self.t_l, self.t_n)}
        return deepcopy_keeping(state, [self.my_model, self])

    def restore(self, snapshot: dict) -> None:
        """Put the model and simulator back in the state of `snapshot`, in place.
        A snapshot can be restored any number of times."""
        state = deepcopy_keeping(snapshot, [self.my_model, self])
        set_model_state(self.my_model, state["model"])
        self.t_l, self.t_n = state["times"]
        self.input = {}
        self.output = {}
        self.initialized = True

    # --- injection ---------------------------------------------------------
    def sim_inject(self, e: float, port_or_bag: str | Bag, value: Any = None) -> None:
        """Inject `value` on input `port` (or a whole bag) `e` after the last event.

        Raises `ValueError` unless `0 <= e <= t_n - t_l`, or if a port is undeclared.
        """
        assert self.my_model is not None
        bag = port_or_bag if isinstance(port_or_bag, dict) else {str(port_or_bag): [value]}
        self.inject_at(self.t_l + e, bag)

    def inject_to(self, model: Any, t: float, bag: Bag) -> None:
        """`inject_at` for the simulated model itself (activity results)."""
        if model is not self.my_model:
            raise ValueError(f"{model!r} is not part of this simulation")
        self.inject_at(t, bag)

    def inject_at(self, t: float, bag: Bag) -> None:
        """Inject `bag` at absolute time `t`, `t_l <= t <= t_n`."""
        _check_injection(self, t, bag, self.my_model._inports)
        if t == self.t_n:  # confluent: λ before δcon
            self.compute_input_output(t)
            self.show_output()
        self.wrap_deltfunc(t, bag)


class _InstantGuard:
    """Counts consecutive rounds at one time; raises past `limit`."""

    __slots__ = ("limit", "t", "count")

    def __init__(self, limit: Optional[int]) -> None:
        self.limit = INFINITY if limit is None else limit
        self.t = -INFINITY
        self.count = 0

    def check(self, t: float) -> None:
        if t != self.t:
            self.t = t
            self.count = 1
            return
        self.count += 1
        if self.count > self.limit:
            raise ZeroTimeLoopError(
                f"more than {self.limit} rounds at time {t}: the model does not advance "
                "time (raise max_rounds_per_instant if this is legitimate)"
            )


def _check_injection(sim: AtomicSimulator, t: float, bag: Bag, inports: list[str]) -> None:
    if not sim.t_l <= t <= sim.t_n:
        raise ValueError(
            f"input rejected at time {sim.t_l}: elapsed time {t - sim.t_l} is outside "
            f"[0, {sim.t_n - sim.t_l}]"
        )
    for port in bag:
        if port not in inports:
            raise ValueError(f"{sim.my_model.get_name()!r} has no input port {port!r}")


def _format_bag(bag: Bag) -> str:
    return " ".join(f"port: {port} value: {v!r}" for port, values in bag.items() for v in values)


def _has_custom_show_state(model: Any) -> bool:
    from devspy.modeling.atomic import Atomic

    if model is None:
        return False
    return type(model).show_state is not Atomic.show_state
