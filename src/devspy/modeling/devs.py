from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

from devspy.modeling.content import Content
from devspy.modeling.entity import Entity
from devspy.modeling.message import Message
from devspy.modeling.port import Port

if TYPE_CHECKING:
    from devspy.simulation.coupled_simulator import CoupledSimulator


class DevsBase(Entity):
    """Root of the DEVS model hierarchy.

    Ports Java's `devs` + `IODevs` into one base class; concrete subclasses
    are `Atomic` and `Digraph`.
    """

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self._parent: Optional["DevsBase"] = None
        self._inports: list[str] = []
        self._outports: list[str] = []

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

    def make_content(self, port: Port | str, value) -> Content:
        return Content(port, value)

    def message_on_port(self, x: Message, port: Port | str, c: Content) -> bool:
        return c.on_port(port)

    def set_parent(self, parent: "DevsBase") -> None:
        self._parent = parent

    def get_parent(self) -> Optional["DevsBase"]:
        return self._parent


class IOBasicDevs(DevsBase, ABC):
    """Abstract base for models that implement the DEVS state-transition contract."""

    @abstractmethod
    def initialize(self) -> None: ...

    @abstractmethod
    def deltint(self) -> None: ...

    @abstractmethod
    def deltext(self, e: float, x: Message) -> None: ...

    @abstractmethod
    def deltcon(self, e: float, x: Message) -> None: ...

    @abstractmethod
    def ta(self) -> float: ...

    @abstractmethod
    def out(self) -> Message: ...

    @abstractmethod
    def show_state(self) -> None: ...

    def set_simulator(self, sim: "CoupledSimulator") -> None:
        self._simulator = sim

    def get_simulator(self) -> Optional["CoupledSimulator"]:
        return getattr(self, "_simulator", None)

    def get_activity(self):
        return None
