from __future__ import annotations

from typing import Iterable, Iterator, List

from devspy.modeling.content import Content
from devspy.modeling.port import Port


class Message:
    """A multiset of Content items (a DEVS bag).

    Order-preserving list semantics; ports may appear multiple times.
    """

    __slots__ = ("_items",)

    def __init__(self, items: Iterable[Content] | None = None) -> None:
        self._items: List[Content] = list(items) if items else []

    def add(self, content: Content) -> None:
        self._items.append(content)

    def is_empty(self) -> bool:
        return not self._items

    def size(self) -> int:
        return len(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[Content]:
        return iter(self._items)

    def m_iterator(self) -> Iterator[Content]:
        return iter(self._items)

    def read(self, i: int) -> Content:
        return self._items[i]

    def on_port(self, port: Port | str, c: Content) -> bool:
        return c.on_port(port)

    def get_val_on_port(self, port: Port | str, c: Content):
        return c.get_value() if self.on_port(port, c) else None

    def values_on_port(self, port_name: str) -> List:
        return [c.get_value() for c in self._items if c.get_port_name() == port_name]

    def print(self) -> None:
        print(self.__repr__())

    def __repr__(self) -> str:
        return " ".join(repr(c) for c in self._items)
