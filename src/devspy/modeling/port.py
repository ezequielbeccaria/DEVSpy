from __future__ import annotations

from devspy.modeling.entity import Entity


class Port(Entity):
    __slots__ = ()

    def __init__(self, name: str) -> None:
        super().__init__(name)
