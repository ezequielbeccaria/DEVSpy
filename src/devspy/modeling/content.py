from __future__ import annotations

from typing import Any, Optional

from devspy.modeling.port import Port


class Content:
    """A (port, value) pair in a message bag.

    The port is kept as its name; a `Port` object is only built if someone asks
    for it (`port` / `get_port()`), since the simulator creates one Content per
    delivered message.
    """

    __slots__ = ("_port_name", "_port", "value")

    def __init__(self, port: Port | str, value: Any) -> None:
        if isinstance(port, Port):
            self._port: Optional[Port] = port
            self._port_name: str = port.get_name()
        else:
            self._port = None
            self._port_name = port
        self.value = value

    @property
    def port(self) -> Port:
        if self._port is None:
            self._port = Port(self._port_name)
        return self._port

    def get_port(self) -> Port:
        return self.port

    def get_port_name(self) -> str:
        return self._port_name

    def get_value(self) -> Any:
        return self.value

    def on_port(self, port: Port | str) -> bool:
        name = port.get_name() if isinstance(port, Port) else port
        return self._port_name == name

    def value_on_port(self, port_name: str) -> Any:
        return self.value if self._port_name == port_name else None

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Content):
            return NotImplemented
        return self._port_name == other._port_name and self.value == other.value

    def __hash__(self) -> int:
        return hash((self._port_name, repr(self.value)))

    def __repr__(self) -> str:
        return f"port: {self._port_name} value: {self.value!r}"
