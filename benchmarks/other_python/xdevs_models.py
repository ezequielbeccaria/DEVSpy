"""xDEVS.py (PyPI `xdevs` 3.0.0) ports of ../devstone_model.py and ../rl_model.py.

Notes on API differences, all neutral for these models:
- default deltcon is deltint(); deltext(0) (DEVSpy/DEVSJAVA pass the real e). The
  only confluent case here applies `continue` to an infinite sigma.
- Coordinator.simulate_time stops at t < t0 + interval, so callers pass horizon + eps.
- Coordinator.initialize() rebuilds the simulator tree; there is no reset, so a
  new Coordinator is built per run/episode.
"""
from xdevs.models import Atomic, Coupled, Port

INF = float("inf")
STATS = {"int": 0, "ext": 0, "sink": 0, "decisions": 0, "reward": 0}
SEED = {"episode": 0}


# --- DEVStone-like ---------------------------------------------------------
class Gen(Atomic):
    def __init__(self, n):
        super().__init__("gen")
        self.o_out = Port(int, "out")
        self.add_out_port(self.o_out)
        self.n = n

    def initialize(self):
        self.k = 0
        self.hold_in("active", 1.0)

    def exit(self):
        pass

    def deltint(self):
        STATS["int"] += 1
        self.k += 1
        if self.k >= self.n:
            self.passivate()
        else:
            self.hold_in("active", 1.0)

    def deltext(self, e):
        pass

    def lambdaf(self):
        self.o_out.add(self.k)


class Proc(Atomic):
    def __init__(self, name):
        super().__init__(name)
        self.i_in, self.o_out = Port(int, "in"), Port(int, "out")
        self.add_in_port(self.i_in)
        self.add_out_port(self.o_out)

    def initialize(self):
        self.count = 0
        self.passivate()

    def exit(self):
        pass

    def deltext(self, e):
        STATS["ext"] += 1
        self.count += len(self.i_in)
        if self.phase == "passive":
            self.hold_in("active", 0.1)
        else:
            self.continuef(e)

    def deltint(self):
        STATS["int"] += 1
        self.passivate()

    def lambdaf(self):
        self.o_out.add(self.count)


class Sink(Atomic):
    def __init__(self):
        super().__init__("sink")
        self.i_in = Port(int, "in")
        self.add_in_port(self.i_in)

    def initialize(self):
        self.passivate()

    def exit(self):
        pass

    def deltint(self):
        pass

    def deltext(self, e):
        STATS["ext"] += 1
        STATS["sink"] += len(self.i_in)
        self.passivate()

    def lambdaf(self):
        pass


class Level(Coupled):
    def __init__(self, width, depth):
        super().__init__(f"L{depth}")
        self.i_in, self.o_out = Port(int, "in"), Port(int, "out")
        self.add_in_port(self.i_in)
        self.add_out_port(self.o_out)
        procs = [Proc(f"P{depth}_{i}") for i in range(width - 1 if depth > 1 else width)]
        for p in procs:
            self.add_component(p)
            self.add_coupling(self.i_in, p.i_in)
        self.add_coupling(procs[0].o_out, self.o_out)
        if depth > 1:
            sub = Level(width, depth - 1)
            self.add_component(sub)
            self.add_coupling(self.i_in, sub.i_in)
            self.add_coupling(sub.o_out, self.o_out)


class DevStoneTop(Coupled):
    def __init__(self, width, depth, n):
        super().__init__("top")
        gen, lv, sink = Gen(n), Level(width, depth), Sink()
        for c in (gen, lv, sink):
            self.add_component(c)
        self.add_coupling(gen.o_out, lv.i_in)
        self.add_coupling(lv.o_out, sink.i_in)


# --- RL-shaped --------------------------------------------------------------
def lcg(x):
    return (x * 1103515245 + 12345) % 2147483648


class Section(Atomic):
    def __init__(self, idx):
        super().__init__(f"S{idx}")
        self.idx = idx
        self.i_act, self.o_obs = Port(int, "act"), Port(int, "obs")
        self.add_in_port(self.i_act)
        self.add_out_port(self.o_obs)

    def initialize(self):
        self.rng = lcg(SEED["episode"] * 7919 + self.idx + 1)
        self.last = 0
        self._travel()

    def exit(self):
        pass

    def _travel(self):
        self.rng = lcg(self.rng)
        self.last = 1 + (self.rng >> 16) % 5
        self.hold_in("travel", self.last)

    def deltint(self):
        if self.phase == "travel":
            self.passivate("wait")
        else:
            self._travel()

    def deltext(self, e):
        for v in self.i_act.values:
            if v // 10 == self.idx and self.phase == "wait":
                self.hold_in("dwell", v % 10)
                return
        self.continuef(e)

    def lambdaf(self):
        if self.phase == "travel":
            self.o_obs.add(self.idx * 1000 + self.last)


class Agent(Atomic):
    def __init__(self):
        super().__init__("agent")
        self.i_obs, self.o_act = Port(int, "obs"), Port(int, "act")
        self.add_in_port(self.i_obs)
        self.add_out_port(self.o_act)

    def initialize(self):
        self.rng = lcg(SEED["episode"] + 424242)
        self.pending = []
        self.passivate()

    def exit(self):
        pass

    def deltext(self, e):
        for o in sorted(self.i_obs.values):
            idx, travel = divmod(o, 1000)
            STATS["reward"] += 3 - abs(travel - 3)
            STATS["decisions"] += 1
            self.rng = lcg(self.rng)
            self.pending.append(idx * 10 + (travel + (self.rng >> 16) % 2) % 4)
        self.hold_in("act", 0.0)

    def deltint(self):
        self.pending = []
        self.passivate()

    def lambdaf(self):
        for a in self.pending:
            self.o_act.add(a)


class RLEnv(Coupled):
    def __init__(self, sections):
        super().__init__("rl_env")
        agent = Agent()
        self.add_component(agent)
        for i in range(sections):
            s = Section(i)
            self.add_component(s)
            self.add_coupling(s.o_obs, agent.i_obs)
            self.add_coupling(agent.o_act, s.i_act)
