from __future__ import annotations

import math
from typing import Optional

from devspy.modeling.atomic import Atomic
from devspy.modeling.content import Content
from devspy.modeling.digraph import Couprel, Digraph
from devspy.modeling.entity import Pair
from devspy.modeling.message import Message
from devspy.simulation.atomic_simulator import AtomicSimulator
from devspy.simulation.coupled_simulator import CoupledSimulator
from devspy.util.logging import FULL, log

INFINITY = math.inf


class Coordinator(AtomicSimulator):
    """Ports DEVSJAVA's `coordinator`.

    Orchestrates a coupled model: each child component gets its own
    `CoupledSimulator` (atomic child) or nested `Coordinator` (digraph child);
    this class routes messages across the coupling relation and advances time
    to the next scheduled event.
    """

    def __init__(self, coupled: Digraph, set_simulators: bool = True) -> None:
        super().__init__(coupled)
        self.my_coupled: Digraph = coupled
        self.cr: Couprel = coupled.get_couprel()
        self.model_to_sim: dict[str, AtomicSimulator] = {}
        self.internal_model_to_sim: dict[str, AtomicSimulator] = {}
        self.simulators: list[AtomicSimulator] = []
        self.coup_info = Couprel()
        self.ext_coup_info = Couprel()
        self.input = Message()
        self.output = Message()
        self.e: float = 0.0
        coupled.set_coordinator(self)
        if set_simulators:
            self._set_simulators()
            self._inform_coupling()

    # --- simulator wiring --------------------------------------------------
    def _set_simulators(self) -> None:
        for component in self.my_coupled.get_components():
            if isinstance(component, Atomic):
                self._add_simulator(component)
            elif isinstance(component, Digraph):
                self._add_coordinator(component)
            else:
                raise RuntimeError(
                    f"Unsupported component type for coordinator: {type(component)!r}"
                )
        self._tell_all_sims_set_mod_to_sim()

    def _add_simulator(self, component: Atomic) -> None:
        sim = CoupledSimulator(component)
        sim.set_root_parent(self)
        self._simulator_created(sim, component)

    def _add_coordinator(self, component: Digraph) -> None:
        sim = Coordinator(component, set_simulators=True)
        sim.set_root_parent(self)  # type: ignore[arg-type]
        self._simulator_created(sim, component)

    def _simulator_created(self, sim: AtomicSimulator, component) -> None:
        self.simulators.append(sim)
        self.model_to_sim[component.get_name()] = sim
        self.internal_model_to_sim[component.get_name()] = sim

    def _tell_all_sims_set_mod_to_sim(self) -> None:
        for sim in self.simulators:
            if hasattr(sim, "set_mod_to_sim"):
                sim.set_mod_to_sim(self.model_to_sim)  # type: ignore[attr-defined]

    def _inform_coupling(self) -> None:
        my_name = self.my_coupled.get_name()
        for src_pair, dst_pair in self.cr.iter_pairs():
            src = src_pair.get_key()
            if src == my_name:
                self.ext_coup_info.add(src_pair, dst_pair)
            else:
                sim = self.model_to_sim.get(src)
                if hasattr(sim, "add_pair"):
                    sim.add_pair(src_pair, dst_pair)  # type: ignore[attr-defined]

    # --- parent wiring (for nested coordinators) --------------------------
    def set_root_parent(self, parent: "Coordinator") -> None:
        self._root_parent = parent

    def get_root_parent(self) -> Optional["Coordinator"]:
        return getattr(self, "_root_parent", None)

    def set_mod_to_sim(self, mts: dict[str, AtomicSimulator]) -> None:
        # Used only when this Coordinator is itself a child of another Coordinator.
        self.model_to_sim = mts

    def add_pair(self, src: Pair, dst: Pair) -> None:
        self.coup_info.add(src, dst)

    def put_messages(self, c: Content) -> None:
        self.input.add(c)

    def put_my_messages(self, c: Content) -> None:
        self.output.add(c)

    # --- time --------------------------------------------------------------
    def next_tn(self) -> float:
        if not self.simulators:
            return INFINITY
        return min(sim.next_tn() for sim in self.simulators)

    def initialize(self, current_time: float = 0.0) -> None:
        for sim in self.simulators:
            sim.initialize(current_time)
        self.t_l = current_time
        self.t_n = self.next_tn()

    # --- transition --------------------------------------------------------
    def compute_input_output(self, time: float) -> None:
        for sim in self.simulators:
            sim.compute_input_output(time)
        for sim in self.simulators:
            if hasattr(sim, "send_messages"):
                sim.send_messages()  # type: ignore[attr-defined]

    def wrap_deltfunc(self, time: float, x: Optional[Message] = None) -> None:
        self._send_down_messages()
        for sim in self.simulators:
            sim.delt_func(time)
        self.t_l = time
        self.t_n = self.next_tn()
        self.input = Message()
        self.output = Message()

    # Keep a `delt_func` alias so parent coordinators can drive us like any sim.
    def delt_func(self, t: float) -> None:
        self.wrap_deltfunc(t)

    def send_messages(self) -> None:
        """When we are nested inside another Coordinator, route our bubbled-up
        output through the parent's coupling info (same protocol as CoupledSimulator)."""
        root = self.get_root_parent()
        if root is None:
            return
        if self.output is None or self.output.is_empty():
            return
        my_name = self.my_coupled.get_name()
        for co in self.output:
            for cp in self.coup_info.translate(my_name, co.get_port().get_name()):
                new_content = Content(str(cp.get_value()), co.get_value())
                target = self.model_to_sim.get(str(cp.get_key()))
                if target is not None and hasattr(target, "put_messages"):
                    target.put_messages(new_content)  # type: ignore[attr-defined]
                else:
                    root.put_my_messages(new_content)
        self.output = Message()

    def _send_down_messages(self) -> None:
        if self.input.is_empty():
            return
        my_name = self.my_coupled.get_name()
        for co in self.input:
            for cp in self.ext_coup_info.translate(my_name, co.get_port().get_name()):
                dst_name = str(cp.get_key())
                dst_port = str(cp.get_value())
                new_content = Content(dst_port, co.get_value())
                target = self.internal_model_to_sim.get(dst_name)
                if target is not None and hasattr(target, "put_messages"):
                    target.put_messages(new_content)  # type: ignore[attr-defined]

    # --- run loops ---------------------------------------------------------
    def simulate(self, num_iter: int) -> None:
        i = 1
        self.t_n = self.next_tn()
        while self.t_n < INFINITY and i <= num_iter:
            log(f"ITERATION {i} ,time: {self.t_n}", FULL)
            self.compute_input_output(self.t_n)
            self.show_output()
            self.wrap_deltfunc(self.t_n)
            self.show_model_state()
            i += 1
        log(f"Terminated Normally at ITERATION {i} ,time: {self.t_n}", FULL)

    # --- state/output display ---------------------------------------------
    def show_model_state(self) -> None:
        for sim in self.simulators:
            sim.show_model_state()

    def sim_inject(self, e: float, port_or_msg, value=None) -> None:
        if isinstance(port_or_msg, Message):
            m = port_or_msg
        else:
            m = Message()
            m.add(Content(str(port_or_msg), value))
        t = self.t_l + e
        if t <= self.next_tn():
            self.input = m
            self.wrap_deltfunc(t)
            self.show_model_state()
