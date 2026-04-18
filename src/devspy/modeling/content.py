from __future__ import annotations

from typing import Any

from devspy.modeling.port import Port


class Content:
    __slots__ = ("port", "value")

    def __init__(self, port: Port | str, value: Any) -> None:
        self.port = port if isinstance(port, Port) else Port(port)
        self.value = value

    def get_port(self) -> Port:
        return self.port

    def get_port_name(self) -> str:
        return self.port.get_name()

    def get_value(self) -> Any:
        return self.value

    def on_port(self, port: Port | str) -> bool:
        name = port.get_name() if isinstance(port, Port) else port
        return self.port.get_name() == name

    def value_on_port(self, port_name: str) -> Any:
        return self.value if self.port.eq(port_name) else None

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Content):
            return NotImplemented
        return self.port == other.port and self.value == other.value

    def __hash__(self) -> int:
        return hash((self.port, repr(self.value)))

    def __repr__(self) -> str:
        return f"port: {self.port.get_name()} value: {self.value!r}"
