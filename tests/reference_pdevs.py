"""A literal Parallel DEVS abstract simulator, used as an oracle for the kernel.

It follows Chow & Zeigler's hierarchical simulator/coordinator protocol with no
optimizations: there is one coordinator per digraph, no flattening, no heap and
no caching, and every round walks the whole hierarchy and translates couplings
level by level. It is slow, but each step can be checked against the formalism:

- simulator:   tN = tL + ta(s); λ only when t == tN; then
               δint if t == tN and x = ∅, δext(s, t - tL, x) if tL <= t < tN,
               δcon(s, x) if t == tN and x ≠ ∅.
- coordinator: tN = min tN_d. At (*, t) it collects λ of IMM(t) = {d | tN_d = t}
               and maps it through EOC. At (x, t) it builds each child's bag from
               EIC (external input) and IC (the collected outputs), and sends
               (x_d, t) to IMM(t) ∪ {d | x_d ≠ ∅}.
"""

from __future__ import annotations

import math
from typing import Union

from devspy import Atomic, Bag, Digraph

INF = math.inf


class RefSimulator:
    def __init__(self, model: Atomic) -> None:
        self.model = model
        self.tl = 0.0
        self.tn = INF

    def init(self, t: float) -> None:
        self.model.initialize()
        self.tl = t
        self.tn = t + self.model.ta()

    def output(self, t: float) -> Bag:
        assert t == self.tn
        return self.model.out() or {}

    def delta(self, t: float, x: Bag) -> None:
        assert self.tl <= t <= self.tn, "bad synchronization"
        if t == self.tn:
            if x:
                self.model.deltcon(t - self.tl, x)
            else:
                self.model.deltint()
        else:
            assert x
            self.model.deltext(t - self.tl, x)
        self.tl = t
        self.tn = t + self.model.ta()


class RefCoordinator:
    def __init__(self, digraph: Digraph) -> None:
        self.g = digraph
        self.name = digraph.get_name()
        self.children: dict[str, Union[RefSimulator, RefCoordinator]] = {}
        for c in digraph.get_components():
            sim = RefSimulator(c) if isinstance(c, Atomic) else RefCoordinator(c)
            self.children[c.get_name()] = sim
        self.couplings = list(digraph.get_couprel().iter_pairs())
        self.tl = 0.0
        self.tn = INF
        self.collected: dict[str, Bag] = {}

    def init(self, t: float) -> None:
        for child in self.children.values():
            child.init(t)
        self.tl = t
        self.tn = min((c.tn for c in self.children.values()), default=INF)

    def output(self, t: float) -> Bag:
        """(*, t): λ of every imminent child, mapped through EOC."""
        assert t == self.tn
        self.collected = {n: c.output(t) for n, c in self.children.items() if c.tn == t}
        y: Bag = {}
        for (src, sp), (dst, dp) in self.couplings:
            if dst == self.name and src in self.collected:
                y.setdefault(dp, []).extend(self.collected[src].get(sp, ()))
        return {p: v for p, v in y.items() if v}

    def delta(self, t: float, x: Bag) -> None:
        """(x, t): route EIC and IC, then δ for IMM(t) ∪ receivers."""
        assert self.tl <= t <= self.tn, "bad synchronization"
        bags: dict[str, Bag] = {n: {} for n in self.children}
        for (src, sp), (dst, dp) in self.couplings:
            if dst == self.name:
                continue  # EOC: handled in output()
            values = x.get(sp, ()) if src == self.name else self.collected.get(src, {}).get(sp, ())
            if values:
                bags[dst].setdefault(dp, []).extend(values)
        for n, child in self.children.items():
            if child.tn == t or bags[n]:
                child.delta(t, bags[n])
        self.collected = {}
        self.tl = t
        self.tn = min((c.tn for c in self.children.values()), default=INF)


def run(digraph: Digraph, end: float, injections=()) -> list[tuple[float, Bag]]:
    """Run the root loop to `end`; return the root outputs as (t, bag) pairs.

    `injections` is a time-sorted list of (t, bag) external inputs on the root's
    input ports, each one an (x, t) message to the root. When t is also the root's
    tN, (*, t) comes first and both are one confluent round.
    """
    root = RefCoordinator(digraph)
    root.init(0.0)
    pending = list(injections)
    outputs = []
    while True:
        t = min(root.tn, pending[0][0] if pending else INF)
        if t > end or t == INF:
            return outputs
        x = pending.pop(0)[1] if pending and pending[0][0] == t else {}
        if t == root.tn:
            y = root.output(t)
            if y:
                outputs.append((t, y))
        root.delta(t, x)
