from __future__ import annotations

import math
from typing import Optional

from devspy.modeling.content import Content
from devspy.modeling.devs import IOBasicDevs
from devspy.modeling.message import Message
from devspy.modeling.port import Port
from devspy.util.logging import FULL, is_enabled, log

INFINITY = math.inf


class AtomicSimulator:
    """Ports DEVSJAVA's `atomicSimulator`.

    Drives a single atomic model through the DEVS state-transition protocol.
    """

    def __init__(self, model: Optional[IOBasicDevs] = None) -> None:
        self.my_model: Optional[IOBasicDevs] = model
        self.t_l: float = 0.0
        self.t_n: float = 0.0
        self.input: Message = Message()
        self.output: Message = Message()
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

    def get_output(self) -> Message:
        return self.output

    def get_input(self) -> Message:
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
        self.wrap_deltfunc(t, Message())

    def wrap_deltfunc(self, t: float, x: Optional[Message] = None) -> None:
        """Ports `wrapDeltfunc(t, x)` — the DEVS state-transition dispatch."""
        assert self.my_model is not None
        if x is None:
            x = self.input
            self.input = Message()
        if x.is_empty() and not self.equal_tn(t):
            return
        if (not x.is_empty()) and self.equal_tn(t):
            e = t - self.t_l
            self.my_model.deltcon(e, x)
        elif self.equal_tn(t):
            self.my_model.deltint()
        elif not x.is_empty():
            e = t - self.t_l
            self.my_model.deltext(e, x)
        self._wrap_deltfunc_hook()
        self.t_l = t
        self.t_n = self.t_l + self.my_model.ta()

    def compute_input_output(self, t: float) -> None:
        assert self.my_model is not None
        if self.equal_tn(t):
            self.output = self.my_model.out()
        else:
            self.output = Message()
        self._compute_input_output_hook()

    # --- show/print --------------------------------------------------------
    def show_model_state(self) -> None:
        assert self.my_model is not None
        if self.custom_show_state or is_enabled(FULL):
            self.my_model.show_state()

    def show_output(self) -> None:
        if self.output is None or self.output.is_empty():
            return
        self.output.print()

    # --- simulation loops --------------------------------------------------
    def simulate(self, num_iter: int) -> None:
        i = 1
        self.t_n = self.next_tn()
        while self.t_n < INFINITY and i <= num_iter:
            if is_enabled(FULL):
                log(f"ITERATION {i} ,time: {self.t_n}", FULL)
            self.compute_input_output(self.t_n)
            self.show_output()
            self.delt_func(self.t_n)
            # delt_func → wrap_deltfunc already updated t_l and t_n.
            self.show_model_state()
            i += 1
        log(f"Terminated Normally at ITERATION {i} ,time: {self.t_n}", FULL)

    # --- injection ---------------------------------------------------------
    def make_message(self) -> Message:
        return Message()

    def sim_inject(self, e: float, port_or_msg, value=None) -> None:
        assert self.my_model is not None
        if isinstance(port_or_msg, Message):
            m = port_or_msg
        else:
            port = port_or_msg if isinstance(port_or_msg, Port) else Port(str(port_or_msg))
            m = Message()
            m.add(Content(port, value))
        t = self.t_l + e
        if e <= self.my_model.ta():
            self.wrap_deltfunc(t, m)
        else:
            log(f"Time: {self.t_l} ,ERROR input rejected : elapsed time {e} out of bounds", FULL)

    # --- hooks (no-ops, kept for parity) ----------------------------------
    def _wrap_deltfunc_hook(self) -> None:
        pass

    def _compute_input_output_hook(self) -> None:
        pass


def _has_custom_show_state(model: Optional[IOBasicDevs]) -> bool:
    from devspy.modeling.atomic import Atomic

    if model is None:
        return False
    return type(model).show_state is not Atomic.show_state
