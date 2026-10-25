from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Iterator, List, Optional

from devspy.modeling.atomic import Atomic
from devspy.modeling.devs import Bag, DevsBase, IOBasicDevs

if TYPE_CHECKING:
    from devspy.simulation.coordinator import Coordinator

#: A coupling endpoint: (component name, port name).
Endpoint = tuple[str, str]


class Couprel:
    """Coupling relation: maps a source `(component, port)` to the set of
    destination `(component, port)` endpoints it is coupled to."""

    def __init__(self) -> None:
        self._map: dict[Endpoint, set[Endpoint]] = defaultdict(set)

    def add(self, src: Endpoint, dst: Endpoint) -> None:
        self._map[src].add(dst)

    def remove(self, src: Endpoint, dst: Endpoint) -> None:
        if src in self._map:
            self._map[src].discard(dst)
            if not self._map[src]:
                del self._map[src]

    def translate(self, src_name: str, port_name: str) -> set[Endpoint]:
        return set(self._map.get((src_name, port_name), ()))

    def iter_pairs(self) -> Iterator[tuple[Endpoint, Endpoint]]:
        for src, dsts in self._map.items():
            for dst in dsts:
                yield src, dst

    def __iter__(self) -> Iterator[tuple[Endpoint, Endpoint]]:
        return self.iter_pairs()


class Coupled(DevsBase):
    """Marker base for coupled models. Ports DEVSJAVA's `Coupled` interface."""

    def get_components(self) -> List[IOBasicDevs]: ...
    def get_couprel(self) -> Couprel: ...


class Digraph(Coupled):
    """Coupled DEVS model: a set of components + a coupling relation.

    Supports atomic and digraph components (hierarchy). Changing the components
    or couplings of a digraph that is being simulated (e.g. from a model's
    transition) reaches the coordinator, which applies the change after the
    current round. Editing `get_couprel()` directly bypasses that.
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
        self._changed(lambda: self._components.remove(component))  # type: ignore[arg-type]

    def remove(self, component: IOBasicDevs | "Digraph" | str) -> None:
        """Remove a component (or the component with that name) and every
        coupling of this digraph that involves it."""
        if isinstance(component, str):
            component = self.with_name(component)  # type: ignore[assignment]
        if component is None or component not in self._components:
            return
        position = self._components.index(component)  # type: ignore[arg-type]
        self._components.remove(component)  # type: ignore[arg-type]
        name = component.get_name()
        dropped = [(s, d) for s, d in self._couprel.iter_pairs() if name in (s[0], d[0])]
        for src, dst in dropped:
            self._couprel.remove(src, dst)

        def undo() -> None:
            self._components.insert(position, component)  # type: ignore[arg-type]
            for src, dst in dropped:
                self._couprel.add(src, dst)

        self._changed(undo)

    def add_coupling(
        self,
        src: DevsBase | str,
        src_port: str,
        dst: DevsBase | str,
        dst_port: str,
    ) -> None:
        self.add_pair((_name(src), src_port), (_name(dst), dst_port))

    def remove_coupling(
        self,
        src: DevsBase | str,
        src_port: str,
        dst: DevsBase | str,
        dst_port: str,
    ) -> None:
        self.remove_pair((_name(src), src_port), (_name(dst), dst_port))

    def add_pair(self, src: Endpoint, dst: Endpoint) -> None:
        if dst in self._couprel.translate(*src):
            return
        self._couprel.add(src, dst)
        self._changed(lambda: self._couprel.remove(src, dst))

    def remove_pair(self, src: Endpoint, dst: Endpoint) -> None:
        if dst not in self._couprel.translate(*src):
            return
        self._couprel.remove(src, dst)
        self._changed(lambda: self._couprel.add(src, dst))

    def _changed(self, undo) -> None:
        """Tell the coordinator, if any. A change it rejects right away (outside a
        round) is undone before the error propagates; changes made inside a
        round are validated when the round ends."""
        if self._coordinator is None:
            return
        try:
            self._coordinator.structure_changed()
        except Exception:
            undo()
            raise

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

    def set_coordinator(self, coordinator: Optional["Coordinator"]) -> None:
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

    def deltext(self, e: float, x: Bag) -> None:
        pass

    def deltcon(self, e: float, x: Bag) -> None:
        pass

    def out(self) -> Bag:
        return {}

    def __repr__(self) -> str:
        return " ".join(repr(c) for c in self._components)


def _name(model: DevsBase | str) -> str:
    return model if isinstance(model, str) else model.get_name()
