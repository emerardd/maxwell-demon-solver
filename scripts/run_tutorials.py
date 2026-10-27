"""Solve only the tutorial levels of a world (hint levels carrying that world's text keys).

Usage: run_tutorials.py GAME_DIR WORLD [seconds per level, default 15]
Quick check after a rule change; the full batch is catalog.py.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mdemon import catalog, mxw, sim, solver, store

levels, structure, _ = mxw.load_world(sys.argv[1])
world = sys.argv[2]
budget = float(sys.argv[3]) if len(sys.argv) > 3 else 15
todo = [lid for kind, lid in catalog.world_levels(structure, levels, world)
        if kind == 'hint' and any(t[2].startswith(world + '/') for t in levels[lid].texts)]
sv = solver.Solver(levels, time_budget=budget)
ok, results, solved_by = 0, {}, {}
for n, lid in enumerate(todo, 1):
    keys = sorted({t[2] for t in levels[lid].texts})
    t = time.time()
    # Some levels are meant to be entered through a hot or cold level block (w3/transition-3):
    # when the neutral outside gives no solution, try the other outside temperatures.
    for t_out in (sim.NEUTRAL, sim.COLD, sim.HOT):
        try:
            r = sv.solve(lid, t_out=t_out)
            status = 'OK' if r and solver.replay(sv, lid, r[0], t_out=t_out)[0] else ('BADPLAN' if r else 'UNSOLVABLE')
            msg = solver.flatten(r[0])[:80] if r else ''
            if status == 'OK':
                store.record(lid, r[0], store.ctx_of(t_out=t_out), 'run_tutorials')
        except TimeoutError:
            status, msg = 'TIMEOUT', ''
        except (RuntimeError, NotImplementedError) as e:
            status, msg = 'ERROR', str(e)
        if status != 'UNSOLVABLE':
            break
    if status == 'OK' and t_out != sim.NEUTRAL:
        msg = f'(outside {sim.TEMP_CHAR[t_out]}) {msg}'
    if status == 'OK':
        for other in r[1] - {lid}:
            solved_by.setdefault(other, lid)
    ok += status == 'OK'
    results[lid] = status
    print(f'[{n}/{len(todo)}] {lid} {status:10} {time.time() - t:5.1f}s  {keys}  {msg}', flush=True)
# A level that cannot be solved on its own may be solved inside another level's solution
# (e.g. it needs to be entered through a cold level block after a third level is solved).
for lid, status in results.items():
    if status != 'OK' and lid in solved_by:
        ok += 1
        print(f'{lid} OK(via {solved_by[lid]}): solved as part of that level, was {status} on its own')
print(f'{world}: {ok}/{len(todo)} tutorial levels solved and replayed')
