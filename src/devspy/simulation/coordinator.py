from __future__ import annotations

import math
from heapq import heapify, heappop, heappush
from operator import attrgetter
from typing import Optional

from devspy.exceptions import ModelStructureError, ZeroTimeLoopError
from devspy.modeling.atomic import Atomic
from devspy.modeling.devs import Bag, DevsBase
from devspy.modeling.digraph import Digraph
from devspy.simulation.atomic_simulator import AtomicSimulator, _check_injection
from devspy.simulation.coupled_simulator import CoupledSimulator, Fanout, Route
from devspy.simulation.observer import deepcopy_keeping, model_state, set_model_state
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

    The network is validated while flattening (`ModelStructureError`), and a run
    that spends more than `max_rounds_per_instant` rounds at a single time
    raises `ZeroTimeLoopError` instead of hanging (`None` disables the check).

    Scheduling: tN = min tN_d and IMM(t) = {d | tN_d = t} come either from a heap
    of `(t_n, index, version)` or from a linear scan of the simulators. The scan
    costs ~n per round, the heap ~k·log2(n) for k reschedules per round, so with
    `scheduler = "auto"` the coordinator measures k and scans while
    n / (k·log2 n) < ~0.42 (dense models), using the heap otherwise. "heap" and
    "scan" force one.

    Variable structure: when a digraph of the hierarchy changes (components or
    couplings added or removed, e.g. from a model's transition), the network is
    re-flattened after the current round, as in DSDEVS. Every transition at t
    sees the old structure, existing simulators keep their state, new atomics
    are initialized at t, and removed ones leave the schedule.
    """

    scheduler: str = "auto"
    _AUTO_PERIOD = 61  # rounds before the first scheduler choice; then doubling
    _AUTO_PERIOD_MAX = 8192

    def __init__(self, coupled: Digraph, set_simulators: bool = True) -> None:
        super().__init__(coupled)
        self.my_coupled: Digraph = coupled
        self.simulators: list[CoupledSimulator] = []
        self.input: Bag = {}
        self.output: Bag = {}
        self.custom_show_state: bool = False
        # (t_n, simulator index, simulator version); stale entries are skipped lazily.
        self._heap: list[tuple[float, int, int]] = []
        # Rebuild the heap when stale entries make it this long (set in _flatten).
        self._heap_limit = 64
        # Linear-scan scheduling instead of the heap (see `scheduler`).
        # Scheduler mode: next_tn/_pop are bound to the heap or scan variant, so
        # the hot path has no mode branch. In "auto" mode _rounds re-chooses after
        # 61, 122, 244, ... rounds; the reschedules in between are the growth of
        # the simulators' version sum (each reschedule bumps exactly one version).
        self._set_scan(self.scheduler == "scan")
        self._reset_choice()
        self._imminent: list[CoupledSimulator] = []
        self._receivers: list[CoupledSimulator] = []
        self._imminent_time: float = -INFINITY
        self._ext_fanout: dict[str, list[Fanout]] = {}
        # Inside a run or a δ phase, structure changes wait for the round to end.
        self._running = False
        self._structure_pending = False
        self._digraphs: list[Digraph] = []
        coupled.set_coordinator(self)
        if set_simulators:
            self._flatten()

    # --- flattening --------------------------------------------------------
    def _flatten(self, reuse: Optional[dict[int, CoupledSimulator]] = None) -> list:
        """(Re)build the simulators and routes from the digraph hierarchy.

        `reuse` maps id(model) to the existing simulator of an atomic that is
        still in the network; those keep their times and state. Returns the
        simulators created for atomics that had none."""
        self._parent: dict[int, Digraph] = {}
        self._children: dict[int, dict[str, object]] = {}
        self.simulators = []
        self._digraphs = []
        sim_of: dict[int, CoupledSimulator] = {}
        fresh: list[CoupledSimulator] = []

        def visit(g: Digraph) -> None:
            g.set_coordinator(self)
            self._digraphs.append(g)
            self._children[id(g)] = _check_components(g)
            for c in g.get_components():
                if isinstance(c, Atomic):
                    sim = reuse.pop(id(c), None) if reuse else None
                    if sim is None:
                        sim = CoupledSimulator(c, len(self.simulators))
                        fresh.append(sim)
                    else:
                        sim.index = len(self.simulators)
                        sim.routes = {}
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
            for pair in _sorted_pairs(g):
                _check_coupling(g, children, pair)
                (src_name, src_port), (dst_name, dst_port) = pair
                child = children.get(src_name)
                if isinstance(child, Atomic) and src_name != g.get_name():
                    routes = sim_of[id(child)].routes.setdefault(src_port, [])
                    self._resolve(g, dst_name, dst_port, routes)
            for c in g.get_components():
                if isinstance(c, Digraph):
                    walk(c)

        walk(self.my_coupled)
        for sim in self.simulators:
            for routes in sim.routes.values():
                if any(dsim is sim for dsim, _ in routes):
                    raise ModelStructureError(
                        f"{sim.my_model.get_name()!r} is coupled to itself; a DEVS model "
                        "cannot receive its own output (use an internal transition)"
                    )
            sim.fanout = {port: _group(routes) for port, routes in sim.routes.items()}
        self.custom_show_state = any(sim.custom_show_state for sim in self.simulators)
        self._heap_limit = 2 * len(self.simulators) + 64
        self._ext_fanout = {}
        return fresh

    # --- variable structure ------------------------------------------------
    def structure_changed(self) -> None:
        """Called by a digraph of this hierarchy after it changed. Re-flattens now,
        or after the current round when called from inside one."""
        if self._running:
            self._structure_pending = True
        else:
            self._restructure()

    def _restructure(self) -> None:
        self._structure_pending = False
        old_digraphs = self._digraphs
        backup = (
            self.simulators, self._parent, self._children, self._sim_of, old_digraphs,
            self._heap_limit, [(s, s.index, s.routes, s.fanout) for s in self.simulators],
        )
        try:
            fresh = self._flatten({id(s.my_model): s for s in self.simulators})
        except Exception:
            (self.simulators, self._parent, self._children, self._sim_of, self._digraphs,
             self._heap_limit, sims) = backup
            for sim, index, routes, fanout in sims:
                sim.index, sim.routes, sim.fanout = index, routes, fanout
            raise
        live = {id(g) for g in self._digraphs}
        for g in old_digraphs:
            if id(g) not in live:
                g.set_coordinator(None)  # type: ignore[arg-type]
        if self.initialized:
            t = self.t_l
            for sim in fresh:  # new atomics start at the current time
                model = sim.my_model
                sim.t_l = t
                model.initialize()
                sim.t_n = t + model.ta()
        self._rebuild_heap()
        self._reset_choice()
        self.t_n = self.next_tn()

    def _resolve(self, g: Digraph, name: str, port: str, out: list[Route]) -> None:
        """Follow a coupling destination `(name, port)` inside digraph `g` down/up to
        atomic input ports (appended to `out`). Couplings are already validated."""
        child = self._children[id(g)].get(name) if name != g.get_name() else None
        if isinstance(child, Atomic):
            out.append((self._sim_of[id(child)], port))
        elif isinstance(child, Digraph):
            for dst_name, dst_port in _sorted_dsts(child, child.get_name(), port):
                self._resolve(child, dst_name, dst_port, out)
        elif g is self.my_coupled:
            out.append((None, port))  # EOC of the root: goes to self.output
        else:
            parent = self._parent[id(g)]
            for dst_name, dst_port in _sorted_dsts(parent, g.get_name(), port):
                self._resolve(parent, dst_name, dst_port, out)

    def _fanout_for_input(self, port: str) -> list[Fanout]:
        fanout = self._ext_fanout.get(port)
        if fanout is None:
            if port not in self.my_coupled._inports:
                raise ModelStructureError(
                    f"{self.my_coupled.get_name()!r} has no input port {port!r}"
                )
            routes: list[Route] = []
            root = self.my_coupled
            for dst_name, dst_port in _sorted_dsts(root, root.get_name(), port):
                self._resolve(root, dst_name, dst_port, routes)
            fanout = _group(routes)
            self._ext_fanout[port] = fanout
        return fanout

    # --- time --------------------------------------------------------------
    def _next_tn_scan(self) -> float:
        return min(map(_get_tn, self.simulators), default=INFINITY)

    def _next_tn_heap(self) -> float:
        heap, sims = self._heap, self.simulators
        while heap:
            tn, idx, version = heap[0]
            if sims[idx].version == version:
                return tn
            heappop(heap)
        return INFINITY

    def initialize(self, current_time: float = 0) -> None:
        show = self.custom_show_state or is_enabled(FULL)
        heap: list[tuple[float, int, int]] = []
        self._running = True  # a model's initialize() may change the structure
        for sim in self.simulators:
            model = sim.my_model
            sim.t_l = current_time
            model.initialize()
            sim.input = {}
            sim.t_n = current_time + model.ta()
            sim.version += 1
            if sim.t_n < INFINITY:
                heap.append((sim.t_n, sim.index, sim.version))
            if show:
                model.show_state()
        heap.sort()
        self._heap = [] if self._scan else heap
        self._reset_choice()
        self._imminent = []
        self._receivers = []
        self._imminent_time = -INFINITY
        self.input = {}
        self.output = {}
        self.t_l = current_time
        self.t_n = self.next_tn()
        self.initialized = True
        self._running = False
        if self._structure_pending:
            self._restructure()

    # --- transition --------------------------------------------------------
    def _pop_scan(self, time: float) -> list[CoupledSimulator]:
        """IMM(time), in simulator index order, by scanning."""
        return [s for s in self.simulators if s.t_n == time]

    def _pop_heap(self, time: float) -> list[CoupledSimulator]:
        """IMM(time), in simulator index order, popped from the heap."""
        heap, sims = self._heap, self.simulators
        imminent: list[CoupledSimulator] = []
        while heap and heap[0][0] <= time:
            tn, idx, version = heappop(heap)
            sim = sims[idx]
            if sim.version == version and tn == time:
                imminent.append(sim)
        return imminent

    def _lambda(
        self, time: float, imminent: list[CoupledSimulator], receivers: list[CoupledSimulator]
    ) -> None:
        """Apply λ to the imminents and route their outputs (appends to `receivers`)."""
        root_out = self.output
        observers = self.observers
        for sim in imminent:
            y = sim.my_model.out()
            if not y:
                continue
            if observers:
                for obs in observers:
                    obs.on_output(time, sim.my_model, y)
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
        # Push while tn < limit: every finite tn in heap mode, nothing in scan mode.
        limit = -INFINITY if self._scan else INFINITY
        observers = self.observers
        for sim in affected:
            model = sim.my_model
            x_bag = sim.input
            old_tn = sim.t_n
            if x_bag:
                sim.input = {}
                if old_tn == time:
                    model.deltcon(time - sim.t_l, x_bag)
                else:
                    model.deltext(time - sim.t_l, x_bag)
            else:
                model.deltint()
            if observers:
                kind = ("con" if old_tn == time else "ext") if x_bag else "int"
                for obs in observers:
                    obs.on_transition(time, model, kind, time - sim.t_l, x_bag)
            sim.t_l = time
            tn = time + (model.sigma if sim.ta_is_sigma else model.ta())
            if tn == old_tn != time:
                # A receiver whose next event did not move: its heap entry
                # (old_tn, index, version) is still valid.
                continue
            sim.t_n = tn
            version = sim.version + 1
            sim.version = version
            if tn < limit:
                push(heap, (tn, sim.index, version))
        if len(heap) > self._heap_limit:
            self._rebuild_heap()

    def _sync_scheduler(self) -> None:
        """Honour a `scheduler` set on the instance after construction."""
        if self.scheduler != "auto" and (self.scheduler == "scan") != self._scan:
            self._set_scan(self.scheduler == "scan")

    def _choose_scheduler(self) -> None:
        """Pick scan or heap from the reschedules per round since the last choice
        (with hysteresis, so a borderline model does not flip every period)."""
        versions = sum(map(_get_version, self.simulators))
        per_round = (versions - self._versions_seen) / max(self._round_count - self._count_seen, 1)
        self._versions_seen, self._count_seen = versions, self._round_count
        self._choice_period = min(2 * self._choice_period, self._AUTO_PERIOD_MAX)
        self._next_choice = self._round_count + self._choice_period
        n = len(self.simulators)
        # scan ~ n per round; heap ~ reschedules * log2(n) per round
        ratio = n / (per_round * max(math.log2(n), 1.0)) if per_round else INFINITY
        if not self._scan and ratio < 0.38:
            self._set_scan(True)
        elif self._scan and ratio > 0.46:
            self._set_scan(False)

    def _reset_choice(self) -> None:
        """Start measuring afresh (versions changed outside rounds: initialize,
        restore, restructure); the next choice comes after _AUTO_PERIOD rounds."""
        self._versions_seen = sum(map(_get_version, self.simulators))
        self._round_count = self._count_seen = 0
        self._choice_period = self._AUTO_PERIOD
        self._next_choice = self._AUTO_PERIOD

    def _set_scan(self, scan: bool) -> None:
        self._scan = scan
        self.next_tn = self._next_tn_scan if scan else self._next_tn_heap  # type: ignore[method-assign]
        self._pop = self._pop_scan if scan else self._pop_heap  # type: ignore[method-assign]
        self._rebuild_heap()  # from the simulators' t_n (empty in scan mode)

    def _rebuild_heap(self) -> None:
        """Drop the stale entries left behind by rescheduled receivers."""
        if self._scan:
            self._heap = []
            return
        heap = [(s.t_n, s.index, s.version) for s in self.simulators if s.t_n < INFINITY]
        heapify(heap)
        self._heap = heap

    def _round(self, time: float) -> None:
        """One full PDEVS round at `time` (λ, routing, δ); root outputs stay in
        `self.output` for the caller to show."""
        imminent = self._pop(time)
        receivers: list[CoupledSimulator] = []
        self._out_t = time
        self._lambda(time, imminent, receivers)
        self._delta(time, imminent, receivers)
        self.t_l = time
        self.t_n = self.next_tn()

    def compute_input_output(self, time: float) -> None:
        self._imminent = self._pop(time)
        self._imminent_time = time
        self._out_t = time
        self._lambda(time, self._imminent, self._receivers)

    def wrap_deltfunc(self, time: float, x: Optional[Bag] = None) -> None:
        if self._imminent_time != time:
            # (x, t) with no preceding (*, t), e.g. sim_inject. At t == t_n the
            # imminents' λ must still run and be routed before their δ.
            self.compute_input_output(time)
        self._send_down_messages()
        running, self._running = self._running, True
        try:
            self._delta(time, self._imminent, self._receivers)
        finally:
            self._running = running
        self._imminent = []
        self._receivers = []
        self._imminent_time = -INFINITY
        self.t_l = time
        self.t_n = self.next_tn()
        self.input = {}
        if self._structure_pending and not running:
            self._restructure()
        if self.output:  # root outputs of this round, shown after it as in _run
            self.show_output()
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
        """Run at most `num_iter` rounds."""
        self._run(num_iter, INFINITY)

    def _run(self, num_iter: float, max_time: float) -> None:
        """Run rounds while `t_n <= max_time`, for at most `num_iter` rounds or until
        `stop_simulation()`. Initializes first if `initialize()` was never called."""
        if not self.initialized:
            self._sync_scheduler()
            self.initialize(0)
        self._sync_scheduler()
        self._stop_sim_flag = False
        self._running = True
        try:
            self._rounds(num_iter, max_time)
        finally:
            self._running = False

    def _rounds(self, num_iter: float, max_time: float) -> None:
        logging_on = is_enabled(FULL)
        show_state = self.custom_show_state or logging_on
        run_round = self._round
        limit = self.max_rounds_per_instant
        if limit is None:
            limit = INFINITY
        last_t, same = -INFINITY, 0
        auto = self.scheduler == "auto"
        next_choice = self._next_choice
        count = self._round_count
        i = 1
        t = self.t_n = self.next_tn()
        while t < INFINITY and t <= max_time and i <= num_iter and not self._stop_sim_flag:
            if logging_on:
                log(f"ITERATION {i} ,time: {t}", FULL)
            if t == last_t:
                same += 1
                if same > limit:
                    raise ZeroTimeLoopError(
                        f"more than {limit} rounds at time {t}: the model does not advance "
                        "time (raise max_rounds_per_instant if this is legitimate)"
                    )
            else:
                last_t, same = t, 1
            run_round(t)
            count += 1
            if auto and count >= next_choice:
                self._round_count = count
                self._choose_scheduler()
                next_choice = self._next_choice
            if self._structure_pending:
                self._restructure()  # restarts the scheduler measurement
                count, next_choice = self._round_count, self._next_choice
            if self.output:
                self.show_output()
                self.output = {}
            if show_state:
                self.show_model_state()
            i += 1
            t = self.t_n
        self._round_count = count
        log(f"Terminated Normally at ITERATION {i} ,time: {self.t_n}", FULL)

    # --- snapshots ---------------------------------------------------------
    def snapshot(self) -> dict:
        """Copy of the simulation state (every atomic's attributes and times; the
        schedule is rebuilt from them), for `restore`. Model objects are not copied, and
        references between models are kept as references."""
        state = {
            "models": [model_state(s.my_model) for s in self.simulators],
            "sims": [(s.t_l, s.t_n, s.version, s.input) for s in self.simulators],
            "times": (self.t_l, self.t_n),
            "structure": [id(s.my_model) for s in self.simulators],
        }
        return deepcopy_keeping(state, self._structure())

    def restore(self, snapshot: dict) -> None:
        """Put every model and simulator back in the state of `snapshot`, in
        place. A snapshot can be restored any number of times."""
        if snapshot["structure"] != [id(s.my_model) for s in self.simulators]:
            raise ValueError("the network structure changed since this snapshot")
        state = deepcopy_keeping(snapshot, self._structure())
        for sim, ms, (t_l, t_n, version, inp) in zip(
            self.simulators, state["models"], state["sims"]
        ):
            set_model_state(sim.my_model, ms)
            sim.t_l, sim.t_n, sim.version, sim.input = t_l, t_n, version, inp
        self._rebuild_heap()
        self._reset_choice()
        self.t_l, self.t_n = state["times"]
        self._imminent = []
        self._receivers = []
        self._imminent_time = -INFINITY
        self.input = {}
        self.output = {}
        self.initialized = True

    def inject_to(self, model, t: float, bag: Bag) -> None:
        """Deliver `bag` straight to input ports of the atomic `model` at time `t`
        (used for activity results): an external event on a hidden root input
        coupled to that model. At `t == t_n` the imminents' λ runs first."""
        sim = getattr(model, "_simulator", None)
        if sim is None or sim.index >= len(self.simulators) or self.simulators[sim.index] is not sim:
            raise ValueError(f"{model!r} is not part of this simulation")
        self.t_n = self.next_tn()
        _check_injection(self, t, bag, model._inports)
        if self._imminent_time != t:
            self.compute_input_output(t)
        inp = sim.input
        if not inp:
            self._receivers.append(sim)
        for port, values in bag.items():
            inp.setdefault(port, []).extend(values)
        self.wrap_deltfunc(t)
        self.show_model_state()

    def _structure(self) -> list:
        """Objects a snapshot keeps by reference: models, digraphs, simulators."""
        objs: list = [self, self.my_coupled, *self.simulators]
        objs.extend(s.my_model for s in self.simulators)
        stack = [self.my_coupled]
        while stack:
            for c in stack.pop().get_components():
                if isinstance(c, Digraph):
                    objs.append(c)
                    stack.append(c)
        return objs

    # --- state/output display ---------------------------------------------
    def show_model_state(self) -> None:
        if not (self.custom_show_state or is_enabled(FULL)):
            return
        for sim in self.simulators:
            sim.show_model_state()

    def sim_inject(self, e: float, port_or_bag: str | Bag, value=None) -> None:
        """Inject `value` on root input `port` (or a whole bag) `e` after the last event.

        Raises `ValueError` unless `0 <= e <= t_n - t_l`, or if a port is undeclared.
        """
        bag = port_or_bag if isinstance(port_or_bag, dict) else {str(port_or_bag): [value]}
        self.inject_at(self.t_l + e, bag)

    def inject_at(self, t: float, bag: Bag) -> None:
        """Inject `bag` on root input ports at absolute time `t`, `t_l <= t <= t_n`.
        At `t == t_n` it is a confluent round: the imminents' λ runs first."""
        self.t_n = self.next_tn()
        _check_injection(self, t, bag, self.my_coupled._inports)
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
_get_tn = attrgetter("t_n")
_get_version = attrgetter("version")


def _check_components(g: Digraph) -> dict[str, DevsBase]:
    """Map component name -> component, rejecting duplicate names (couplings are
    keyed by name) and names that shadow the digraph's own."""
    children: dict[str, DevsBase] = {}
    for c in g.get_components():
        name = c.get_name()
        if name in children or name == g.get_name():
            raise ModelStructureError(
                f"digraph {g.get_name()!r}: duplicate component name {name!r}"
            )
        children[name] = c
    return children


def _check_coupling(g: Digraph, children: dict[str, DevsBase], pair) -> None:
    """A coupling of `g` must be EIC (g.in -> child.in), IC (child.out -> child.in)
    or EOC (child.out -> g.out), between declared ports."""
    (src_name, src_port), (dst_name, dst_port) = pair
    me = g.get_name()
    where = f"digraph {me!r}: coupling {src_name}.{src_port} -> {dst_name}.{dst_port}"
    if src_name == me:
        if dst_name == me:
            raise ModelStructureError(f"{where} connects an input straight to an output")
        src_ports, src_kind = g._inports, "input"
    else:
        src = children.get(src_name)
        if src is None:
            raise ModelStructureError(f"{where}: unknown component {src_name!r}")
        src_ports, src_kind = src._outports, "output"
    if dst_name == me:
        dst_ports, dst_kind = g._outports, "output"
    else:
        dst = children.get(dst_name)
        if dst is None:
            raise ModelStructureError(f"{where}: unknown component {dst_name!r}")
        dst_ports, dst_kind = dst._inports, "input"
    if src_port not in src_ports:
        raise ModelStructureError(f"{where}: {src_name!r} has no {src_kind} port {src_port!r}")
    if dst_port not in dst_ports:
        raise ModelStructureError(f"{where}: {dst_name!r} has no {dst_kind} port {dst_port!r}")


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
