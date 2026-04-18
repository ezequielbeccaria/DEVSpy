from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Hashable


class Entity:
    def __init__(self, name: str = "anEntity") -> None:
        self.name = name

    def get_name(self) -> str:
        return self.name

    def eq(self, name: str) -> bool:
        return self.name == name

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Entity):
            return NotImplemented
        return self.name == other.name

    def __hash__(self) -> int:
        return hash(self.name)

    def __repr__(self) -> str:
        return self.name


class IntEnt(Entity):
    def __init__(self, value: int, name: str | None = None) -> None:
        super().__init__(name if name is not None else str(value))
        self.value = int(value)

    def __int__(self) -> int:
        return self.value


class DoubleEnt(Entity):
    def __init__(self, value: float, name: str | None = None) -> None:
        super().__init__(name if name is not None else str(value))
        self.value = float(value)

    def __float__(self) -> float:
        return self.value


@dataclass(frozen=True)
class Pair:
    """Immutable (key, value) pair used for DEVS coupling specs.

    Hashable so it can be stored in dicts/sets, matching GenCol.Pair semantics.
    """

    key: Hashable
    value: Hashable

    def get_key(self) -> Any:
        return self.key

    def get_value(self) -> Any:
        return self.value
