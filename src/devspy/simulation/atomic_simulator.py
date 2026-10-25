from __future__ import annotations

import math
from typing import Any, Optional

from devspy.modeling.devs import Bag, IOBasicDevs
from devspy.util.logging import FULL, is_enabled, log

INFINITY = math.inf


class AtomicSimulator:
    """Drives a single atomic model through the DEVS state-transition protocol."""

    __slots__ = ("my_model", "t_l", "t_n", "input", "output", "custom_show_state", "__dict__")

    def __init__(self, model: Any = None) -> None:
        # Any, not IOBasicDevs: Coordinator passes its Digraph here.
        self.my_model: Any = model
        self.t_l: float = 0.0
        self.t_n: float = 0.0
        self.input: Bag = {}
        self.output: Bag = {}
        # The default Atomic.show_state only logs; skip calling it when logging is off.
        self.custom_show_state: bool = _has_custom_show_state(model)

    # --- time accessors ----------------------------------------------------
    def next_tn(self) -> float:
        return self.t_n

    def equal_tn(self, t: float) -> bool:
        return t == self.t_n

    def get_tn(self) -> float:
        return self.t_n

    def get_tl(self) -> float:
        return self.t_l

    def get_output(self) -> Bag:
        return self.output

    def get_input(self) -> Bag:
        return self.input

    def get_model(self) -> Optional[IOBasicDevs]:
        return self.my_model

    # --- lifecycle ---------------------------------------------------------
    def initialize(self, current_time: float = 0.0) -> None:
        assert self.my_model is not None
        self.my_model.initialize()
        self.t_l = current_time
        self.t_n = self.t_l + self.my_model.ta()
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
            self.my_model.deltcon(t - self.t_l, x)
        elif t == self.t_n:
            self.my_model.deltint()
        else:
            self.my_model.deltext(t - self.t_l, x)
        self.t_l = t
        self.t_n = self.t_l + self.my_model.ta()

    def compute_input_output(self, t: float) -> None:
        assert self.my_model is not None
        self.output = (self.my_model.out() or {}) if t == self.t_n else {}

    # --- show/print --------------------------------------------------------
    def show_model_state(self) -> None:
        assert self.my_model is not None
        if self.custom_show_state or is_enabled(FULL):
            self.my_model.show_state()

    def show_output(self) -> None:
        if self.output:
            print(_format_bag(self.output))

    # --- simulation loops --------------------------------------------------
    def simulate(self, num_iter: float) -> None:
        i = 1
        self.t_n = self.next_tn()
        while self.t_n < INFINITY and i <= num_iter:
            if is_enabled(FULL):
                log(f"ITERATION {i} ,time: {self.t_n}", FULL)
            self.compute_input_output(self.t_n)
            self.show_output()
            self.delt_func(self.t_n)
            self.show_model_state()
            i += 1
        log(f"Terminated Normally at ITERATION {i} ,time: {self.t_n}", FULL)

    # --- injection ---------------------------------------------------------
    def sim_inject(self, e: float, port_or_bag: str | Bag, value: Any = None) -> None:
        """Inject `value` on input `port` (or a whole bag) `e` after the last event."""
        assert self.my_model is not None
        bag = port_or_bag if isinstance(port_or_bag, dict) else {str(port_or_bag): [value]}
        t = self.t_l + e
        if e <= self.my_model.ta():
            self.wrap_deltfunc(t, bag)
        else:
            log(f"Time: {self.t_l} ,ERROR input rejected : elapsed time {e} out of bounds", FULL)


def _format_bag(bag: Bag) -> str:
    return " ".join(f"port: {port} value: {v!r}" for port, values in bag.items() for v in values)


def _has_custom_show_state(model: Any) -> bool:
    from devspy.modeling.atomic import Atomic

    if model is None:
        return False
    return type(model).show_state is not Atomic.show_state
