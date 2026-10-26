"""Solve a level as met inside its real parent, with chosen levels already solved.

Usage: solve_in_context.py GAME_DIR LEVEL SECONDS [SOLVED_ID ...]
The search starts inside LEVEL as if just entered through its real block in its real parent
(from the first free side of that block), so it may leave to the parent (through a shortcut)
and come back. It succeeds once LEVEL is solved.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mdemon import mxw, sim, solver
from mdemon.context import context_start

if __name__ == '__main__':
    levels = mxw.load_world(sys.argv[1])[0]
    lid, budget = sys.argv[2], float(sys.argv[3])
    solved = frozenset(sys.argv[4:])
    for kw in (dict(heuristic='informed', h_weight=3), dict()):
        sv = solver.Solver(levels, time_budget=budget, **kw)
        h0 = context_start(sv, lid, solved)
        t = time.time()
        try:
            r = sv.solve(lid, start=h0, goal=lambda h: lid in h.solved)
        except TimeoutError:
            print(f'{kw or "A*"}: timeout ({time.time() - t:.1f}s, {len(sv.last_search[0]):,} states)')
            continue
        if r is None:
            print(f'{kw or "A*"}: no solution ({time.time() - t:.1f}s, {len(sv.last_search[0]):,} states)')
            continue
        print(f'{kw or "A*"}: solved in {time.time() - t:.1f}s: {solver.flatten(r[0])}')
        break
