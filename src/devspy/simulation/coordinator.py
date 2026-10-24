from __future__ import annotations

import math
from heapq import heappop, heappush
from operator import attrgetter
from typing import Optional

from devspy.modeling.atomic import Atomic
from devspy.modeling.devs import Bag
from devspy.modeling.digraph import Digraph
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
        self.input: Bag = {}
        self.output: Bag = {}
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
            for (src_name, src_port), (dst_name, dst_port) in _sorted_pairs(g):
                child = children.get(src_name)
                if isinstance(child, Atomic) and src_name != g.get_name():
                    routes = sim_of[id(child)].routes.setdefault(src_port, [])
                    self._resolve(g, dst_name, dst_port, routes, from_input=False)
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
            for dst_name, dst_port in _sorted_dsts(child, child.get_name(), port):
                self._resolve(child, dst_name, dst_port, out, from_input=True)
        elif from_input:
            # An input coupled straight to an output (or to an unknown name) is not a
            # valid DEVS coupling; dropped, as the hierarchical coordinator did.
            return
        elif g is self.my_coupled:
            out.append((None, port))  # EOC of the root: goes to self.output
        else:
            parent = self._parent[id(g)]
            for dst_name, dst_port in _sorted_dsts(parent, g.get_name(), port):
                self._resolve(parent, dst_name, dst_port, out, from_input=False)

    def _fanout_for_input(self, port: str) -> list[Fanout]:
        fanout = self._ext_fanout.get(port)
        if fanout is None:
            routes: list[Route] = []
            root = self.my_coupled
            for dst_name, dst_port in _sorted_dsts(root, root.get_name(), port):
                self._resolve(root, dst_name, dst_port, routes, from_input=True)
            fanout = _group([r for r in routes if r[0] is not None])
            self._ext_fanout[port] = fanout
        return fanout

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
            sim.input = {}
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
        self.input = {}
        self.output = {}
        self.t_l = current_time
        self.t_n = self.next_tn()

    # --- transition --------------------------------------------------------
    def _pop(self, time: float) -> list[CoupledSimulator]:
        """Pop IMM(time) from the heap, in simulator index order."""
        heap, sims = self._heap, self.simulators
        imminent: list[CoupledSimulator] = []
        while heap and heap[0][0] <= time:
            tn, idx, version = heappop(heap)
            sim = sims[idx]
            if sim.version == version and tn == time:
                imminent.append(sim)
        return imminent

    def _lambda(self, imminent: list[CoupledSimulator], receivers: list[CoupledSimulator]) -> None:
        """Apply λ to the imminents and route their outputs (appends to `receivers`)."""
        root_out = self.output
        for sim in imminent:
            y = sim.my_model.out()
            if not y:
                continue
            fanout = sim.fanout
            for src_port, values in y.items():
                groups = fanout.get(src_port)
                if not groups or not values:
                    continue
                for port, dsims in groups:
                    for dsim in dsims:
                        # Each receiver gets its own list: senders may reuse theirs.
                        inp = root_out if dsim is None else dsim.input
                        if not inp and dsim is not None:
                            receivers.append(dsim)
                        lst = inp.get(port)
                        if lst is None:
                            inp[port] = list(values)
                        else:
                            lst.extend(values)

    def _delta(
        self, time: float, imminent: list[CoupledSimulator], receivers: list[CoupledSimulator]
    ) -> None:
        """Apply δ to IMM(time) ∪ INF(time) in index order and reschedule them."""
        others = [s for s in receivers if s.t_n != time]
        if others:
            affected = imminent + others
            affected.sort(key=_by_index)
        else:
            affected = imminent
        heap = self._heap
        push = heappush
        inf = INFINITY
        for sim in affected:
            model = sim.my_model
            x_bag = sim.input
            if x_bag:
                sim.input = {}
                if sim.t_n == time:
                    model.deltcon(time - sim.t_l, x_bag)
                else:
                    model.deltext(time - sim.t_l, x_bag)
            else:
                model.deltint()
            sim.t_l = time
            tn = time + (model.sigma if sim.ta_is_sigma else model.ta())
            sim.t_n = tn
            version = sim.version + 1
            sim.version = version
            if tn < inf:
                push(heap, (tn, sim.index, version))

    def _round(self, time: float) -> None:
        """One full PDEVS round at `time` (λ, routing, δ); root outputs stay in
        `self.output` for the caller to show."""
        imminent = self._pop(time)
        receivers: list[CoupledSimulator] = []
        self._lambda(imminent, receivers)
        self._delta(time, imminent, receivers)
        self.t_l = time
        self.t_n = self.next_tn()

    def compute_input_output(self, time: float) -> None:
        self._imminent = self._pop(time)
        self._imminent_time = time
        self._lambda(self._imminent, self._receivers)

    def wrap_deltfunc(self, time: float, x: Optional[Bag] = None) -> None:
        self._send_down_messages()
        if self._imminent_time != time:
            # δ without a preceding λ (sim_inject at an event time): the
            # imminents still take their internal/confluent transition.
            self._imminent = self._pop(time)
        self._delta(time, self._imminent, self._receivers)
        self._imminent = []
        self._receivers = []
        self._imminent_time = -INFINITY
        self.t_l = time
        self.t_n = self.next_tn()
        self.input = {}
        self.output = {}

    def delt_func(self, t: float) -> None:
        self.wrap_deltfunc(t)

    def _send_down_messages(self) -> None:
        if not self.input:
            return
        receivers = self._receivers
        for src_port, values in self.input.items():
            for port, dsims in self._fanout_for_input(src_port):
                for dsim in dsims:
                    if dsim is None:
                        continue
                    inp = dsim.input
                    if not inp:
                        receivers.append(dsim)
                    inp.setdefault(port, []).extend(values)

    # --- run loops ---------------------------------------------------------
    def simulate(self, num_iter: int) -> None:
        i = 1
        self.t_n = self.next_tn()
        while self.t_n < INFINITY and i <= num_iter:
            if is_enabled(FULL):
                log(f"ITERATION {i} ,time: {self.t_n}", FULL)
            self._round(self.t_n)
            if self.output:
                self.show_output()
                self.output = {}
            if self.custom_show_state:
                self.show_model_state()
            i += 1
        log(f"Terminated Normally at ITERATION {i} ,time: {self.t_n}", FULL)

    # --- state/output display ---------------------------------------------
    def show_model_state(self) -> None:
        if not (self.custom_show_state or is_enabled(FULL)):
            return
        for sim in self.simulators:
            sim.show_model_state()

    def sim_inject(self, e: float, port_or_bag: str | Bag, value=None) -> None:
        """Inject `value` on root input `port` (or a whole bag) `e` after the last event."""
        bag = port_or_bag if isinstance(port_or_bag, dict) else {str(port_or_bag): [value]}
        t = self.t_l + e
        if t <= self.next_tn():
            self.input = {port: list(values) for port, values in bag.items()}
            self.wrap_deltfunc(t)
            self.show_model_state()


def _group(routes: list[Route]) -> list[Fanout]:
    """[(sim, port), ...] -> [(port, [sim, ...]), ...], keeping first-seen order."""
    groups: dict[str, list] = {}
    for dsim, port in routes:
        groups.setdefault(port, []).append(dsim)
    return list(groups.items())


_by_index = attrgetter("index")


def _sorted_pairs(g: Digraph):
    # Couprel stores destinations in sets; sort for a run-to-run deterministic order.
    return sorted(g.get_couprel().iter_pairs(), key=_pair_key)


def _sorted_dsts(g: Digraph, name: str, port: str):
    return sorted(g.get_couprel().translate(name, port), key=_dst_key)


def _pair_key(p):
    (src_name, src_port), (dst_name, dst_port) = p
    return (str(src_name), str(src_port), str(dst_name), str(dst_port))


def _dst_key(d):
    return (str(d[0]), str(d[1]))
