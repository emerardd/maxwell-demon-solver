"""Solve one level and print the world state after every step of the plan.

Usage: trace_plan.py GAME_DIR LEVEL [seconds, default 15]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mdemon import mxw, sim, solver, world

levels = mxw.load_world(sys.argv[1])[0]
lid = sys.argv[2]
sv = solver.Solver(levels, time_budget=float(sys.argv[3]) if len(sys.argv) > 3 else 15)
plan, _ = sv.solve(lid)
w = sv.world
h = w.start(lid)


def show(label, h):
    if not h.path:
        print(f'{label}: finished, solved={sorted(h.solved)}')
        return
    m = w.current(h)
    print(f'{label}: path={[(f.lid, sim.TEMP_CHAR[f.t_out], f.dir) for f in h.path]} solved={sorted(h.solved)}')
    print(m.render(h.top))


show('start', h)
for step in plan:
    if isinstance(step, str):
        for letter in step:
            h = w.step(h, sim.DIR_NAMES.index(letter))
            show(letter, h)
            if not h.path:
                break
    elif step[0] == 'enter':
        h = w.enter(h, sim.DIR_NAMES.index(step[1]))
        show(f'enter {step[1]}', h)
    else:
        h = w.quit(h)
        show('quit', h)
