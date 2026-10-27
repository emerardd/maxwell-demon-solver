"""Solve a level and print it in a form that is easy to try in the game.

Usage: show_solution.py GAME_DIR LEVEL [seconds, default 60]
Prints the starting map, then the moves in groups of 5 with arrows, each group followed by the
map after it, so a mismatch in the game can be found quickly.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mdemon import mxw, sim, solver, store
from mdemon.report import walkthrough

if __name__ == '__main__':
    levels = mxw.load_world(sys.argv[1])[0]
    lid = sys.argv[2]
    budget = float(sys.argv[3]) if len(sys.argv) > 3 else 60
    sv, plan, _ = solver.solve_any(levels, lid, budget)
    assert solver.replay(sv, lid, plan)[0], 'plan does not replay'
    store.record(lid, plan, source='show_solution')
    walkthrough(sv, lid, plan)
