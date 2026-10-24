from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from devspy.modeling.content import Content
from devspy.modeling.devs import IOBasicDevs
from devspy.modeling.digraph import Couprel
from devspy.modeling.entity import Pair
from devspy.modeling.message import Message
from devspy.simulation.atomic_simulator import AtomicSimulator

if TYPE_CHECKING:
    from devspy.simulation.coordinator import Coordinator


class CoupledSimulator(AtomicSimulator):
    """Wraps a single atomic model living inside a `Coordinator`.

    Knows its parent coordinator, holds per-model coupling info, and routes
    its own `out()` messages to sibling simulators via `send_messages`.
    """

    def __init__(self, model: IOBasicDevs) -> None:
        super().__init__(model)
        self.model_to_sim: dict[str, "AtomicSimulator"] = {}
        self.coup_info = Couprel()
        self._parent: Optional["Coordinator"] = None
        self._root_parent: Optional["Coordinator"] = None
        model.set_simulator(self)

    # --- parent / coupling setup ------------------------------------------
    def set_parent(self, parent: "Coordinator") -> None:
        self._parent = parent

    def set_root_parent(self, parent: "Coordinator") -> None:
        self._root_parent = parent

    def get_parent(self) -> Optional["Coordinator"]:
        return self._parent

    def get_root_parent(self) -> Optional["Coordinator"]:
        return self._root_parent

    def set_mod_to_sim(self, mts: dict[str, "AtomicSimulator"]) -> None:
        self.model_to_sim = mts

    def add_pair(self, src: Pair, dst: Pair) -> None:
        self.coup_info.add(src, dst)

    def remove_pair(self, src: Pair, dst: Pair) -> None:
        self.coup_info.remove(src, dst)

    # --- message handling --------------------------------------------------
    def put_messages(self, c: Content) -> None:
        self.input.add(c)

    def convert_msg(self, x: Message) -> list[tuple[str, Content]]:
        """Translate our output bag via local coupling into (dst_name, content) tuples."""
        assert self.my_model is not None
        result: list[tuple[str, Content]] = []
        if x.is_empty():
            return result
        my_name = self.my_model.get_name()
        for co in x:
            for cp in self.coup_info.translate(my_name, co.get_port().get_name()):
                new_content = Content(str(cp.get_value()), co.get_value())
                result.append((str(cp.get_key()), new_content))
        return result

    def send_messages(self) -> None:
        out_msg = self.get_output()
        if out_msg is None or out_msg.is_empty():
            return
        for dst_name, co in self.convert_msg(out_msg):
            target = self.model_to_sim.get(dst_name)
            if isinstance(target, CoupledSimulator):
                target.put_messages(co)
            elif target is not None and hasattr(target, "put_messages"):
                target.put_messages(co)  # type: ignore[attr-defined]
            else:
                # No sibling → this is an internal→external coupling, bubble up.
                if self._parent is not None:
                    self._parent.put_my_messages(co)
                elif self._root_parent is not None:
                    self._root_parent.put_my_messages(co)

    def delt_func(self, t: float) -> None:
        self.wrap_deltfunc(t, self.input)
        self.input = Message()

    def simulate(self, num_iter: float) -> None:
        i = 1
        self.t_n = self.next_tn()
        from devspy.modeling.atomic import INFINITY
        while self.t_n < INFINITY and i <= num_iter:
            self.compute_input_output(self.t_n)
            self.show_output()
            self.send_messages()
            self.delt_func(self.t_n)
            self.show_model_state()
            i += 1
