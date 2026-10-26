"""Solve single levels and print the plans. Usage: solve_one.py GAME_DIR SECONDS LEVEL[@SCOPE] ...

LEVEL@SCOPE starts the search in SCOPE (an ancestor) and stops once LEVEL is solved.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mdemon import mxw, solver

levels = mxw.load_world(sys.argv[1])[0]
sv = solver.Solver(levels, time_budget=float(sys.argv[2]))
for arg in sys.argv[3:]:
    lid, _, scope = arg.partition('@')
    t = time.time()
    try:
        r = sv.solve(lid, scope=scope or None)
        if r is None:
            print(f'{arg}: UNSOLVABLE ({time.time() - t:.1f}s)', flush=True)
        else:
            ok = solver.replay(sv, lid, r[0], scope=scope or None)[0]
            print(f'{arg}: {"OK" if ok else "BADPLAN"} ({time.time() - t:.1f}s) {solver.flatten(r[0])}', flush=True)
    except TimeoutError:
        print(f'{arg}: TIMEOUT ({time.time() - t:.1f}s)', flush=True)
