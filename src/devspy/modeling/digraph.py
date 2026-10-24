from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Iterator, List, Optional

from devspy.modeling.atomic import Atomic
from devspy.modeling.devs import DevsBase, IOBasicDevs
from devspy.modeling.entity import Pair
from devspy.modeling.message import Message

if TYPE_CHECKING:
    from devspy.simulation.coordinator import Coordinator


class Couprel:
    """Coupling relation: maps `Pair(src_component, src_port)` to a set of
    `Pair(dst_component, dst_port)` destinations.

    Equivalent to DEVSJAVA's `couprel` backed by a multi-valued Relation.
    """

    def __init__(self) -> None:
        self._map: dict[Pair, set[Pair]] = defaultdict(set)

    def add(self, src: Pair, dst: Pair) -> None:
        self._map[src].add(dst)

    def remove(self, src: Pair, dst: Pair) -> None:
        if src in self._map:
            self._map[src].discard(dst)
            if not self._map[src]:
                del self._map[src]

    def translate(self, src_name: str, port_name: str) -> set[Pair]:
        return set(self._map.get(Pair(src_name, port_name), set()))

    def iter_pairs(self) -> Iterator[tuple[Pair, Pair]]:
        for src, dsts in self._map.items():
            for dst in dsts:
                yield src, dst

    def __iter__(self) -> Iterator[tuple[Pair, Pair]]:
        return self.iter_pairs()


class Coupled(DevsBase):
    """Marker base for coupled models. Ports DEVSJAVA's `Coupled` interface."""

    def get_components(self) -> List[IOBasicDevs]: ...
    def get_couprel(self) -> Couprel: ...


class Digraph(Coupled):
    """Coupled DEVS model: a set of components + a coupling relation.

    Supports atomic and digraph components (hierarchy).
    """

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self._components: List[IOBasicDevs] = []
        self._couprel = Couprel()
        self._coordinator: Optional["Coordinator"] = None

    # --- composition -------------------------------------------------------
    def add(self, component: IOBasicDevs | "Digraph") -> None:
        self._components.append(component)  # type: ignore[arg-type]
        component.set_parent(self)

    def remove(self, component: IOBasicDevs | "Digraph") -> None:
        if component in self._components:
            self._components.remove(component)  # type: ignore[arg-type]

    def add_coupling(
        self,
        src: DevsBase,
        src_port: str,
        dst: DevsBase,
        dst_port: str,
    ) -> None:
        self._couprel.add(
            Pair(src.get_name(), src_port),
            Pair(dst.get_name(), dst_port),
        )

    def add_pair(self, src: Pair, dst: Pair) -> None:
        self._couprel.add(src, dst)

    def remove_pair(self, src: Pair, dst: Pair) -> None:
        self._couprel.remove(src, dst)

    def with_name(self, name: str) -> Optional[IOBasicDevs]:
        for c in self._components:
            if c.get_name() == name:
                return c  # type: ignore[return-value]
        return None

    def get_components(self) -> List[IOBasicDevs]:
        return list(self._components)

    def get_couprel(self) -> Couprel:
        return self._couprel

    def __iter__(self) -> Iterator[IOBasicDevs]:
        return iter(self._components)

    # --- lifecycle helpers -------------------------------------------------
    def initialize(self) -> None:
        for c in self._components:
            if isinstance(c, (Atomic, Digraph)):
                c.initialize()

    def show_state(self) -> None:
        for c in self._components:
            if hasattr(c, "show_state"):
                c.show_state()

    def set_coordinator(self, coordinator: "Coordinator") -> None:
        self._coordinator = coordinator

    def get_coordinator(self) -> Optional["Coordinator"]:
        return self._coordinator

    def check_name_uniqueness(self, name: str) -> bool:
        return all(c.get_name() != name for c in self._components)

    # --- digraph-level DEVS contract (no-op for plain digraph) -------------
    def ta(self) -> float:
        return 0.0

    def deltint(self) -> None:
        pass

    def deltext(self, e: float, x: Message) -> None:
        pass

    def deltcon(self, e: float, x: Message) -> None:
        pass

    def out(self) -> Message:
        return Message()

    def __repr__(self) -> str:
        return " ".join(repr(c) for c in self._components)
