"""Time TrackRailway episodes with a seeded random agent and reset() per episode.

usage: python trackrailway_bench.py PATH/TO/examples/three_stops N_TRAINS EPISODES
"""
import json
import statistics
import sys
import time
sys.path.insert(0, sys.argv[1])
from devspy import DevsSuiteFacade
from rldevspy import RLEnvironment
from agent import RandomAgent
from _n_train_builder import build_n_train_three_stops_env_event_driven_dense as build

n_trains, episodes = int(sys.argv[2]), int(sys.argv[3])
env = build(num_trains=n_trains, simulation_time=7200.0, seed=0)
agent = RandomAgent(seed=0)
f = DevsSuiteFacade(RLEnvironment(agent, env, name="bench"))
ep = []
for _ in range(episodes):
    t0 = time.perf_counter()
    f.reset()
    f.simulate_to_time(7200.0)
    ep.append((time.perf_counter() - t0) * 1e3)
print(json.dumps({"trains": n_trains, "episodes": episodes, "ep_ms_median": statistics.median(ep), "ep_ms_first": ep[0]}))
