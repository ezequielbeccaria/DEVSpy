"""RL-environment-shaped benchmark model (mirrors java/RLBench.java).

M track sections each run a train: travel (random 1..5 time units) -> arrive
(emit observation) -> wait for the agent's action -> dwell d (0..3) -> travel.
The Agent atomic receives every arrival as an observation, picks a dwell with a
tiny policy (+ exploration noise) and sends the action back in zero time, as an
RL agent embedded in the DEVS model does in RLDEVSpy. Everything is integer and
seeded with the same LCG as the Java port, so `reward`/`decisions` must match
across engines exactly.
"""
from devspy import Atomic, Digraph

SEED = {"episode": 0}
STATS = {"decisions": 0, "reward": 0}


def lcg(x):
    return (x * 1103515245 + 12345) % 2147483648


class Section(Atomic):
    def __init__(self, idx):
        super().__init__(f"S{idx}")
        self.idx = idx
        self.add_inport("act")
        self.add_outport("obs")

    def initialize(self):
        self.rng = lcg(SEED["episode"] * 7919 + self.idx + 1)
        self.last = 0
        self._travel()

    def _travel(self):
        self.rng = lcg(self.rng)
        self.last = 1 + (self.rng >> 16) % 5
        self.hold_in("travel", self.last)

    def deltint(self):
        if self.phase_is("travel"):
            self.passivate_in("wait")
        else:  # dwell finished
            self._travel()

    def deltext(self, e, x):
        for v in x.get("act", ()):
            if v // 10 == self.idx and self.phase_is("wait"):
                self.hold_in("dwell", v % 10)
                return
        self.cont(e)

    def out(self):
        return {"obs": [self.idx * 1000 + self.last]} if self.phase_is("travel") else {}


class Agent(Atomic):
    def __init__(self):
        super().__init__("agent")
        self.add_inport("obs")
        self.add_outport("act")

    def initialize(self):
        self.rng = lcg(SEED["episode"] + 424242)
        self.pending = []
        self.passivate()

    def deltext(self, e, x):
        obs = sorted(x.get("obs", ()))
        for o in obs:
            idx, travel = divmod(o, 1000)
            STATS["reward"] += 3 - abs(travel - 3)
            STATS["decisions"] += 1
            self.rng = lcg(self.rng)
            dwell = (travel + (self.rng >> 16) % 2) % 4
            self.pending.append(idx * 10 + dwell)
        self.hold_in("act", 0.0)

    def deltint(self):
        self.pending = []
        self.passivate()

    def out(self):
        return {"act": list(self.pending)} if self.pending else {}


def build(sections):
    g = Digraph("rl_env")
    agent = Agent()
    g.add(agent)
    for i in range(sections):
        s = Section(i)
        g.add(s)
        g.add_coupling(s, "obs", agent, "obs")
        g.add_coupling(agent, "act", s, "act")
    return g
