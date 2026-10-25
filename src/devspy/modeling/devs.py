from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from devspy.simulation.coupled_simulator import CoupledSimulator

#: A DEVS message bag: input or output port name -> values received/emitted on
#: it at one instant. Models read inputs with ``x.get("in", ())`` and return
#: outputs as ``{"out": [value]}`` (or ``{}`` for no output). Values are plain
#: Python objects.
Bag = Dict[str, List[Any]]


class DevsBase(ABC):
    """Root of the DEVS model hierarchy: a named model with input/output ports.

    Concrete subclasses are `Atomic` and `Digraph`.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._parent: Optional["DevsBase"] = None
        self._inports: list[str] = []
        self._outports: list[str] = []

    def get_name(self) -> str:
        return self.name

    def add_inport(self, port_name: str) -> None:
        if port_name not in self._inports:
            self._inports.append(port_name)

    def add_outport(self, port_name: str) -> None:
        if port_name not in self._outports:
            self._outports.append(port_name)

    def remove_inport(self, port_name: str) -> None:
        if port_name in self._inports:
            self._inports.remove(port_name)

    def remove_outport(self, port_name: str) -> None:
        if port_name in self._outports:
            self._outports.remove(port_name)

    def get_inports(self) -> list[str]:
        return list(self._inports)

    def get_outports(self) -> list[str]:
        return list(self._outports)

    def set_parent(self, parent: "DevsBase") -> None:
        self._parent = parent

    def get_parent(self) -> Optional["DevsBase"]:
        return self._parent

    def __repr__(self) -> str:
        return self.name


class IOBasicDevs(DevsBase):
    """Abstract base for models that implement the DEVS state-transition contract."""

    @abstractmethod
    def initialize(self) -> None: ...

    @abstractmethod
    def deltint(self) -> None: ...

    @abstractmethod
    def deltext(self, e: float, x: Bag) -> None: ...

    @abstractmethod
    def deltcon(self, e: float, x: Bag) -> None: ...

    @abstractmethod
    def ta(self) -> float: ...

    @abstractmethod
    def out(self) -> Bag: ...

    @abstractmethod
    def show_state(self) -> None: ...

    def set_simulator(self, sim: "CoupledSimulator") -> None:
        self._simulator = sim

    def get_simulator(self) -> Optional["CoupledSimulator"]:
        return getattr(self, "_simulator", None)
