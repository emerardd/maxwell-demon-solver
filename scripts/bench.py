"""Compare search configurations on a few levels.

Usage: bench.py GAME_DIR SECONDS LEVEL[@SCOPE] ...
Each configuration is (name, heuristic, h_weight). Prints, per level and configuration, whether
it was solved, the time, the states expanded and the plan length (moves, entries and quits).
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mdemon import mxw, solver

CONFIGS = [('A admissible greedy', 'admissible', 50),
           ('B informed  w=3   ', 'informed', 3),
           ('C informed  greedy', 'informed', 50)]

levels = mxw.load_world(sys.argv[1])[0]
budget = float(sys.argv[2])
for arg in sys.argv[3:]:
    lid, _, scope = arg.partition('@')
    for name, heuristic, weight in CONFIGS:
        sv = solver.Solver(levels, time_budget=budget, heuristic=heuristic, h_weight=weight)
        t = time.time()
        try:
            r = sv.solve(lid, scope=scope or None)
            states = len(sv.last_search[0])
            if r is None:
                status, length = 'UNSOLVABLE', ''
            else:
                ok = solver.replay(sv, lid, r[0], scope=scope or None)[0]
                status, length = ('OK' if ok else 'BADPLAN'), f'{len(solver.flatten(r[0]))} chars'
        except TimeoutError:
            status, length, states = 'TIMEOUT', '', len(sv.last_search[0])
        print(f'{lid} {name}: {status:10} {time.time() - t:5.1f}s {states:8,} states  {length}', flush=True)
