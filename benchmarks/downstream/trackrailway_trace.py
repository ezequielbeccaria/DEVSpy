"""Run TrackRailway episodes (seeded random agent, reset between episodes) and print
one digest per configuration. Run it against two DEVSpy/RLDEVSpy/TrackRailway stacks
and diff the output.

usage: python trackrailway_trace.py PATH/TO/RLDEVSpy-TrackRailway/examples/three_stops
"""
import hashlib
import sys
sys.path.insert(0, sys.argv[1])  # examples/three_stops of the checkout under test
from devspy import DevsSuiteFacade
from rldevspy import RLEnvironment
from agent import RandomAgent
from _n_train_builder import build_n_train_three_stops_env_event_driven_dense as build

class Rec(RandomAgent):
    def policy(self, state):
        a = super().policy(state)
        obs = getattr(state, "observation", state)
        h = hashlib.sha256(repr(sorted((k, getattr(v, "tobytes", lambda: repr(v))()) for k, v in obs.items())).encode()).hexdigest()[:12] if isinstance(obs, dict) else repr(obs)
        LOG.append(f"{h} {a!r} {self.total_reward:.6f}")
        return a

total = hashlib.sha256()
for n in (1, 3, 5):
    for seed in range(3):
        LOG = []
        env = build(num_trains=n, simulation_time=7200.0, seed=seed)
        agent = Rec(seed=seed)
        f = DevsSuiteFacade(RLEnvironment(agent, env, name="e2e"))
        for ep in range(3):
            f.reset()
            f.simulate_to_time(7200.0)
            LOG.append(f"END ep={ep} reward={agent.total_reward:.6f}")
        d = hashlib.sha256("\n".join(LOG).encode()).hexdigest()[:16]
        total.update(d.encode())
        print(f"trains={n} seed={seed} decisions={sum(1 for line in LOG if not line.startswith('END'))} sha={d}")
print("ALL", total.hexdigest()[:16])
