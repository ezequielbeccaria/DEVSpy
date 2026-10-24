from __future__ import annotations

import math
from heapq import heappop, heappush
from typing import Optional

from devspy.modeling.atomic import Atomic
from devspy.modeling.content import Content
from devspy.modeling.digraph import Digraph
from devspy.modeling.message import Message
from devspy.simulation.atomic_simulator import AtomicSimulator
from devspy.simulation.coupled_simulator import CoupledSimulator, Fanout, Route
from devspy.util.logging import FULL, is_enabled, log

INFINITY = math.inf


class Coordinator(AtomicSimulator):
    """Parallel DEVS coordinator for a `Digraph` hierarchy.

    The hierarchy is a modelling construct only. At construction the tree is
    flattened: every atomic gets a `CoupledSimulator` (in depth-first component
    order) and every coupling path, through any number of EIC/IC/EOC levels, is
    resolved into a direct route from an atomic output port to atomic input
    ports, or to the root digraph's output ports.

    Each round at time t follows the PDEVS abstract simulator: λ for the
    imminent models IMM(t) (popped from a heap of t_n), routing of their
    outputs, then δ for IMM(t) ∪ INF(t), the imminents plus the models that
    received input. No other model is touched.
    """

    def __init__(self, coupled: Digraph, set_simulators: bool = True) -> None:
        super().__init__(coupled)
        self.my_coupled: Digraph = coupled
        self.simulators: list[CoupledSimulator] = []
        self.input = Message()
        self.output = Message()
        self.custom_show_state: bool = False
        # (t_n, simulator index, simulator version); stale entries are skipped lazily.
        self._heap: list[tuple[float, int, int]] = []
        self._imminent: list[CoupledSimulator] = []
        self._receivers: list[CoupledSimulator] = []
        self._imminent_time: float = -INFINITY
        self._ext_fanout: dict[str, list[Fanout]] = {}
        coupled.set_coordinator(self)
        if set_simulators:
            self._flatten()

    # --- flattening --------------------------------------------------------
    def _flatten(self) -> None:
        self._parent: dict[int, Digraph] = {}
        self._children: dict[int, dict[str, object]] = {}
        sim_of: dict[int, CoupledSimulator] = {}

        def visit(g: Digraph) -> None:
            g.set_coordinator(self)
            self._children[id(g)] = {c.get_name(): c for c in g.get_components()}
            for c in g.get_components():
                if isinstance(c, Atomic):
                    sim = CoupledSimulator(c, len(self.simulators))
                    self.simulators.append(sim)
                    sim_of[id(c)] = sim
                elif isinstance(c, Digraph):
                    self._parent[id(c)] = g
                    visit(c)
                else:
                    raise RuntimeError(
                        f"Unsupported component type for coordinator: {type(c)!r}"
                    )

        visit(self.my_coupled)
        self._sim_of = sim_of

        def walk(g: Digraph) -> None:
            children = self._children[id(g)]
            for src, dst in _sorted_pairs(g):
                child = children.get(src.get_key())
                if isinstance(child, Atomic) and src.get_key() != g.get_name():
                    routes = sim_of[id(child)].routes.setdefault(src.get_value(), [])
                    self._resolve(g, dst.get_key(), dst.get_value(), routes, from_input=False)
            for c in g.get_components():
                if isinstance(c, Digraph):
                    walk(c)

        walk(self.my_coupled)
        for sim in self.simulators:
            sim.fanout = {port: _group(routes) for port, routes in sim.routes.items()}
        self.custom_show_state = any(sim.custom_show_state for sim in self.simulators)

    def _resolve(
        self, g: Digraph, name: str, port: str, out: list[Route], from_input: bool
    ) -> None:
        """Follow a coupling destination `(name, port)` inside digraph `g` down/up to
        atomic input ports (appended to `out`). `from_input` marks EIC context."""
        child = self._children[id(g)].get(name) if name != g.get_name() else None
        if isinstance(child, Atomic):
            out.append((self._sim_of[id(child)], port))
        elif isinstance(child, Digraph):
            for dst in _sorted_dsts(child, child.get_name(), port):
                self._resolve(child, dst.get_key(), dst.get_value(), out, from_input=True)
        elif from_input:
            # An input coupled straight to an output (or to an unknown name) is not a
            # valid DEVS coupling; dropped, as the hierarchical coordinator did.
            return
        elif g is self.my_coupled:
            out.append((None, port))  # EOC of the root: goes to self.output
        else:
            parent = self._parent[id(g)]
            for dst in _sorted_dsts(parent, g.get_name(), port):
                self._resolve(parent, dst.get_key(), dst.get_value(), out, from_input=False)

    def _fanout_for_input(self, port: str) -> list[Fanout]:
        fanout = self._ext_fanout.get(port)
        if fanout is None:
            routes: list[Route] = []
            root = self.my_coupled
            for dst in _sorted_dsts(root, root.get_name(), port):
                self._resolve(root, dst.get_key(), dst.get_value(), routes, from_input=True)
            fanout = _group([r for r in routes if r[0] is not None])
            self._ext_fanout[port] = fanout
        return fanout

    # --- compatibility with the hierarchical API ---------------------------
    def put_messages(self, c: Content) -> None:
        self.input.add(c)

    def put_my_messages(self, c: Content) -> None:
        self.output.add(c)

    # --- time --------------------------------------------------------------
    def next_tn(self) -> float:
        heap, sims = self._heap, self.simulators
        while heap:
            tn, idx, version = heap[0]
            if sims[idx].version == version:
                return tn
            heappop(heap)
        return INFINITY

    def initialize(self, current_time: float = 0.0) -> None:
        show = self.custom_show_state or is_enabled(FULL)
        heap: list[tuple[float, int, int]] = []
        for sim in self.simulators:
            model = sim.my_model
            model.initialize()
            sim.input = Message()
            sim.t_l = current_time
            sim.t_n = current_time + model.ta()
            sim.version += 1
            if sim.t_n < INFINITY:
                heap.append((sim.t_n, sim.index, sim.version))
            if show:
                model.show_state()
        heap.sort()
        self._heap = heap
        self._imminent = []
        self._receivers = []
        self._imminent_time = -INFINITY
        self.input = Message()
        self.output = Message()
        self.t_l = current_time
        self.t_n = self.next_tn()

    # --- transition --------------------------------------------------------
    def _pop_imminent(self, time: float) -> list[CoupledSimulator]:
        heap, sims = self._heap, self.simulators
        imminent: list[CoupledSimulator] = []
        while heap and heap[0][0] <= time:
            tn, idx, version = heappop(heap)
            sim = sims[idx]
            if sim.version == version and tn == time:
                imminent.append(sim)
        self._imminent = imminent
        self._imminent_time = time
        return imminent

    def compute_input_output(self, time: float) -> None:
        receivers = self._receivers
        root_out = self.output
        for sim in self._pop_imminent(time):
            y = sim.my_model.out()
            sim.output = y
            fanout = sim.fanout
            for c in y._items:
                src_port = c.get_port_name()
                groups = fanout.get(src_port)
                if not groups:
                    continue
                for port, dsims in groups:
                    # Contents are shared by every receiver of the same port.
                    co = c if port == src_port else Content(port, c.value)
                    for dsim in dsims:
                        if dsim is None:
                            root_out.add(co)
                            continue
                        items = dsim.input._items
                        if not items:
                            receivers.append(dsim)
                        items.append(co)

    def wrap_deltfunc(self, time: float, x: Optional[Message] = None) -> None:
        self._send_down_messages()
        if self._imminent_time != time:
            # δ without a preceding λ (sim_inject at an event time): the
            # imminents still take their internal/confluent transition.
            self._pop_imminent(time)
        imminent = self._imminent
        others = [s for s in self._receivers if s.t_n != time]
        affected = imminent + others if others else imminent
        if others:
            affected.sort(key=_index)
        heap = self._heap
        push = heappush
        inf = INFINITY
        for sim in affected:
            model = sim.my_model
            x_bag = sim.input
            if x_bag._items:
                sim.input = Message()
                if sim.t_n == time:
                    model.deltcon(time - sim.t_l, x_bag)
                else:
                    model.deltext(time - sim.t_l, x_bag)
            else:
                model.deltint()
            sim.t_l = time
            tn = time + model.ta()
            sim.t_n = tn
            version = sim.version + 1
            sim.version = version
            if tn < inf:
                push(heap, (tn, sim.index, version))
        self._imminent = []
        self._receivers = []
        self._imminent_time = -INFINITY
        self.t_l = time
        self.t_n = self.next_tn()
        self.input = Message()
        self.output = Message()

    def delt_func(self, t: float) -> None:
        self.wrap_deltfunc(t)

    def _send_down_messages(self) -> None:
        if self.input.is_empty():
            return
        receivers = self._receivers
        for c in self.input:
            for port, dsims in self._fanout_for_input(c.get_port_name()):
                co = c if port == c.get_port_name() else Content(port, c.get_value())
                for dsim in dsims:
                    items = dsim.input._items
                    if not items:
                        receivers.append(dsim)
                    items.append(co)

    # --- run loops ---------------------------------------------------------
    def simulate(self, num_iter: int) -> None:
        i = 1
        self.t_n = self.next_tn()
        while self.t_n < INFINITY and i <= num_iter:
            if is_enabled(FULL):
                log(f"ITERATION {i} ,time: {self.t_n}", FULL)
            self.compute_input_output(self.t_n)
            self.show_output()
            self.wrap_deltfunc(self.t_n)
            self.show_model_state()
            i += 1
        log(f"Terminated Normally at ITERATION {i} ,time: {self.t_n}", FULL)

    # --- state/output display ---------------------------------------------
    def show_model_state(self) -> None:
        if not (self.custom_show_state or is_enabled(FULL)):
            return
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


def _group(routes: list[Route]) -> list[Fanout]:
    """[(sim, port), ...] -> [(port, [sim, ...]), ...], keeping first-seen order."""
    groups: dict[str, list] = {}
    for dsim, port in routes:
        groups.setdefault(port, []).append(dsim)
    return list(groups.items())


def _index(sim: CoupledSimulator) -> int:
    return sim.index


def _sorted_pairs(g: Digraph):
    # Couprel stores destinations in sets; sort for a run-to-run deterministic order.
    return sorted(g.get_couprel().iter_pairs(), key=_pair_key)


def _sorted_dsts(g: Digraph, name: str, port: str):
    return sorted(g.get_couprel().translate(name, port), key=_dst_key)


def _pair_key(p):
    src, dst = p
    return (str(src.get_key()), str(src.get_value()), str(dst.get_key()), str(dst.get_value()))


def _dst_key(d):
    return (str(d.get_key()), str(d.get_value()))
