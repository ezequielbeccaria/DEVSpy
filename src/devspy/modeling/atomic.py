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

    # --- variable structure (applied after the current round) ------------
    def add_model(self, model: IOBasicDevs) -> None:
        """Add `model` to this model's parent digraph. It starts at the current
        time once the round ends."""
        self._parent_digraph().add(model)

    def remove_model(self, model: IOBasicDevs | str) -> None:
        """Remove `model` (or the sibling with that name) and its couplings."""
        self._parent_digraph().remove(model)

    def add_coupling(self, src, src_port: str, dst, dst_port: str) -> None:
        """Couple two components (models or names) of the parent digraph."""
        self._parent_digraph().add_coupling(src, src_port, dst, dst_port)

    def remove_coupling(self, src, src_port: str, dst, dst_port: str) -> None:
        self._parent_digraph().remove_coupling(src, src_port, dst, dst_port)

    def _parent_digraph(self):
        parent = self.get_parent()
        if parent is None:
            raise RuntimeError(f"{self.get_name()!r} is not inside a digraph")
        return parent

    # --- DEVS contract -----------------------------------------------------
    def ta(self) -> float:
        return self.sigma

    def deltint(self) -> None:
        """Internal transition. Override in subclasses."""

    def deltext(self, e: float, x: Bag) -> None:
        """External transition. `x` maps input port -> values received. Override."""

    def deltcon(self, e: float, x: Bag) -> None:
        """Confluent transition. Parallel DEVS default (Chow & Zeigler):
        δcon(s, x) = δext(δint(s), 0, x). The input arrives just after the internal
        transition, so the elapsed time in the new state is 0, not `e`."""
        self.deltint()
        self.deltext(0.0, x)

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
