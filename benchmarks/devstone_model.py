"""DEVStone-LI-like model used by every benchmark in this folder.

Gen emits one event per time unit (N events) into a hierarchy of depth D whose
levels hold W-1 processors (W at the leaf) plus the next level; the first
processor of each level is coupled to the level's output, which reaches Sink.
Every port implementation (java/, cpp/, other_python/) mirrors this exactly, and
the STATS counters must match across engines.
"""

from devspy import Atomic, Digraph

STATS = {"int": 0, "ext": 0, "sink": 0}


class Gen(Atomic):
    def __init__(self, n):
        super().__init__("gen")
        self.add_outport("out")
        self.n = n

    def initialize(self):
        self.k = 0
        self.hold_in("active", 1.0)

    def deltint(self):
        STATS["int"] += 1
        self.k += 1
        if self.k >= self.n:
            self.passivate()
        else:
            self.hold_in("active", 1.0)

    def deltext(self, e, x):
        pass

    def out(self):
        return {"out": [self.k]}


class Proc(Atomic):
    def __init__(self, name):
        super().__init__(name)
        self.add_inport("in")
        self.add_outport("out")

    def initialize(self):
        self.count = 0
        self.passivate()

    def deltext(self, e, x):
        STATS["ext"] += 1
        self.count += len(x.get("in", ()))
        if self.phase_is("passive"):
            self.hold_in("active", 0.1)
        else:
            self.cont(e)

    def deltint(self):
        STATS["int"] += 1
        self.passivate()

    def out(self):
        return {"out": [self.count]}


class Sink(Atomic):
    def __init__(self):
        super().__init__("sink")
        self.add_inport("in")

    def initialize(self):
        self.passivate()

    def deltint(self):
        pass

    def deltext(self, e, x):
        STATS["ext"] += 1
        STATS["sink"] += sum(len(v) for v in x.values())
        self.passivate()

    def out(self):
        return {}


def level(width, depth):
    g = Digraph(f"L{depth}")
    g.add_inport("in")
    g.add_outport("out")
    procs = [Proc(f"P{depth}_{i}") for i in range(width - 1 if depth > 1 else width)]
    for p in procs:
        g.add(p)
        g.add_coupling(g, "in", p, "in")
    g.add_coupling(procs[0], "out", g, "out")
    if depth > 1:
        sub = level(width, depth - 1)
        g.add(sub)
        g.add_coupling(g, "in", sub, "in")
        g.add_coupling(sub, "out", g, "out")
    return g


def build(width, depth, events):
    top = Digraph("top")
    gen, sink, lv = Gen(events), Sink(), level(width, depth)
    for c in (gen, lv, sink):
        top.add(c)
    top.add_coupling(gen, "out", lv, "in")
    top.add_coupling(lv, "out", sink, "in")
    return top
