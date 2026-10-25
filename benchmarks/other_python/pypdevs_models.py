"""PythonPDEVS *minimal* kernel ports of ../devstone_model.py and ../rl_model.py.

Source: github.com/capocchi/PythonPDEVS (PyPDEVS 2.4.1, Python 2), converted
with lib2to3 to run on CPython 3. The minimal kernel flattens the hierarchy
(direct connection) and uses an event scheduler; it has no initialize/reset, so
state is set in __init__ and a new model + Simulator is built per run/episode.
Its termination check is `t >= end`, so callers pass horizon + eps.
Default confTransition sets elapsed = 0 (Zeigler); neutral for these models.
"""
from pypdevs.minimal import AtomicDEVS, CoupledDEVS

INF = float("inf")
STATS = {"int": 0, "ext": 0, "sink": 0, "decisions": 0, "reward": 0}
SEED = {"episode": 0}


class _A(AtomicDEVS):
    def hold_in(self, phase, sigma):
        self.phase, self.sigma = phase, sigma

    def timeAdvance(self):
        return self.sigma


# --- DEVStone-like ---------------------------------------------------------
class Gen(_A):
    def __init__(self, n):
        super().__init__("gen")
        self.out = self.addOutPort("out")
        self.n, self.k = n, 0
        self.hold_in("active", 1.0)

    def intTransition(self):
        STATS["int"] += 1
        self.k += 1
        self.hold_in("passive", INF) if self.k >= self.n else self.hold_in("active", 1.0)
        return self.state

    def outputFnc(self):
        return {self.out: [self.k]}


class Proc(_A):
    def __init__(self, name):
        super().__init__(name)
        self.inp, self.out = self.addInPort("in"), self.addOutPort("out")
        self.count = 0
        self.hold_in("passive", INF)

    def extTransition(self, inputs):
        STATS["ext"] += 1
        self.count += len(inputs.get(self.inp, ()))
        if self.phase == "passive":
            self.hold_in("active", 0.1)
        elif self.sigma < INF:
            self.sigma -= self.elapsed
        return self.state

    def intTransition(self):
        STATS["int"] += 1
        self.hold_in("passive", INF)
        return self.state

    def outputFnc(self):
        return {self.out: [self.count]}


class Sink(_A):
    def __init__(self):
        super().__init__("sink")
        self.inp = self.addInPort("in")
        self.hold_in("passive", INF)

    def extTransition(self, inputs):
        STATS["ext"] += 1
        STATS["sink"] += len(inputs.get(self.inp, ()))
        return self.state

    def outputFnc(self):
        return {}


class Level(CoupledDEVS):
    def __init__(self, width, depth):
        super().__init__(f"L{depth}")
        self.inp, self.out = self.addInPort("in"), self.addOutPort("out")
        procs = [self.addSubModel(Proc(f"P{depth}_{i}"))
                 for i in range(width - 1 if depth > 1 else width)]
        for p in procs:
            self.connectPorts(self.inp, p.inp)
        self.connectPorts(procs[0].out, self.out)
        if depth > 1:
            sub = self.addSubModel(Level(width, depth - 1))
            self.connectPorts(self.inp, sub.inp)
            self.connectPorts(sub.out, self.out)


class DevStoneTop(CoupledDEVS):
    def __init__(self, width, depth, n):
        super().__init__("top")
        gen = self.addSubModel(Gen(n))
        lv = self.addSubModel(Level(width, depth))
        sink = self.addSubModel(Sink())
        self.connectPorts(gen.out, lv.inp)
        self.connectPorts(lv.out, sink.inp)


# --- RL-shaped --------------------------------------------------------------
def lcg(x):
    return (x * 1103515245 + 12345) % 2147483648


class Section(_A):
    def __init__(self, idx):
        super().__init__(f"S{idx}")
        self.idx = idx
        self.act, self.obs = self.addInPort("act"), self.addOutPort("obs")
        self.rng = lcg(SEED["episode"] * 7919 + idx + 1)
        self.last = 0
        self._travel()

    def _travel(self):
        self.rng = lcg(self.rng)
        self.last = 1 + (self.rng >> 16) % 5
        self.hold_in("travel", self.last)

    def intTransition(self):
        if self.phase == "travel":
            self.hold_in("wait", INF)
        else:
            self._travel()
        return self.state

    def extTransition(self, inputs):
        for v in inputs.get(self.act, ()):
            if v // 10 == self.idx and self.phase == "wait":
                self.hold_in("dwell", v % 10)
                return self.state
        if self.sigma < INF:
            self.sigma -= self.elapsed
        return self.state

    def outputFnc(self):
        return {self.obs: [self.idx * 1000 + self.last]} if self.phase == "travel" else {}


class Agent(_A):
    def __init__(self):
        super().__init__("agent")
        self.obs, self.act = self.addInPort("obs"), self.addOutPort("act")
        self.rng = lcg(SEED["episode"] + 424242)
        self.pending = []
        self.hold_in("passive", INF)

    def extTransition(self, inputs):
        for o in sorted(inputs.get(self.obs, ())):
            idx, travel = divmod(o, 1000)
            STATS["reward"] += 3 - abs(travel - 3)
            STATS["decisions"] += 1
            self.rng = lcg(self.rng)
            self.pending.append(idx * 10 + (travel + (self.rng >> 16) % 2) % 4)
        self.hold_in("act", 0.0)
        return self.state

    def intTransition(self):
        self.pending = []
        self.hold_in("passive", INF)
        return self.state

    def outputFnc(self):
        return {self.act: list(self.pending)} if self.pending else {}


class RLEnv(CoupledDEVS):
    def __init__(self, sections):
        super().__init__("rl_env")
        agent = self.addSubModel(Agent())
        for i in range(sections):
            s = self.addSubModel(Section(i))
            self.connectPorts(s.obs, agent.obs)
            self.connectPorts(agent.act, s.act)
