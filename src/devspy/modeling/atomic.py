from __future__ import annotations

import math

from devspy.modeling.devs import Bag, IOBasicDevs
from devspy.util.logging import FULL, is_enabled, log

INFINITY = math.inf


class Atomic(IOBasicDevs):
    """Base class for atomic DEVS models.

    Subclasses override `initialize`, `deltint`, `deltext`, `deltcon`, `out`.
    State is represented by `(phase, sigma)` just like DEVSJAVA.
    """

    def __init__(self, name: str = "atomic") -> None:
        super().__init__(name)
        self.sigma: float = INFINITY
        self.phase: str = "passive"

    # --- lifecycle ---------------------------------------------------------
    def initialize(self) -> None:
        """Set initial `(phase, sigma)`. Override in subclasses."""

    # --- state helpers -----------------------------------------------------
    def set_sigma(self, sigma: float) -> None:
        self.sigma = sigma

    def get_sigma(self) -> float:
        return self.sigma

    def get_phase(self) -> str:
        return self.phase

    def phase_is(self, phase: str) -> bool:
        return self.phase == phase

    def hold_in(self, phase: str, sigma: float) -> None:
        self.phase = phase
        self.sigma = sigma

    def passivate_in(self, phase: str) -> None:
        self.phase = phase
        self.sigma = INFINITY

    def passivate(self) -> None:
        self.phase = "passive"
        self.sigma = INFINITY

    def cont(self, e: float) -> None:
        """Continue: decrement sigma by elapsed time e (was `Continue` in Java)."""
        if self.sigma < INFINITY:
            self.sigma -= e

    # --- DEVS contract -----------------------------------------------------
    def ta(self) -> float:
        return self.sigma

    def deltint(self) -> None:
        """Internal transition. Override in subclasses."""

    def deltext(self, e: float, x: Bag) -> None:
        """External transition. `x` maps input port -> values received. Override."""

    def deltcon(self, e: float, x: Bag) -> None:
        """Confluent transition. DEVSJAVA default: deltint then deltext."""
        self.deltint()
        self.deltext(e, x)

    def out(self) -> Bag:
        """Output function: return {port: [values]} ({} for no output). Override."""
        return {}

    # --- introspection -----------------------------------------------------
    def __str__(self) -> str:
        return f"phase :{self.phase} sigma : {self.sigma}"

    def show_state(self) -> None:
        if not is_enabled(FULL):
            return
        log(f"Model {self.get_name()}'s state: ", FULL)
        log(f"phase :{self.phase} sigma : {self.sigma}", FULL)

    def string_state(self) -> str:
        return ""
