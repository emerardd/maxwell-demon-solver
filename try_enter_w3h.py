"""Can the demon get into w3-H from the w3 map by cooling its hot real block with a cold block?

Usage: try_enter_w3h.py GAME_DIR [seconds, default 60]
Searches on the w3 map (w3 taken as solved) for entering w3-H, guided by: while w3-H's block is
hot, the walking distance from the nearest cold block to it; then the demon's distance to it.
Entering any other level is cut.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mxw, prune, sim, solver

H, W3 = 'b35a381c', '214a0e55'
levels, structure, _ = mxw.load_world(sys.argv[1])
budget = float(sys.argv[2]) if len(sys.argv) > 2 else 60
import run_world
w3node = run_world.find(structure['root'], W3)
# by the time a player gets to extra level H, w3 and its numbered levels are solved
solved = frozenset({W3} | {ch['id'] for ch in w3node.get('normalSublevels', [])})
sv = solver.Solver(levels, time_budget=budget, h_weight=3)
w = sv.world
wm = w.model(W3, solved, sim.NEUTRAL)
hbi = wm.real_block[H]
hb = wm.initial_pos[hbi]
doors = [(hb[0] + dx, hb[1] + dy) for dx, dy in sim.DIRS]
tables = sv.pruner.tables(wm)


def guide(x):
    if not x.path or x.path[-1].lid not in (W3, H):
        return prune.INF
    if x.path[-1].lid == H:
        return 0
    s = x.top
    if s.temp[hbi] == sim.HOT:
        colds = [p for j, p in enumerate(s.pos) if p is not None and s.temp[j] == sim.COLD
                 and not wm.bodies[j].fixed and wm.bodies[j].weight]
        return 50 + min((tables.walk(wm, c).get(d, 999) for c in colds for d in doors), default=999)
    return min(tables.walk(wm, s.demon).get(d, 999) for d in doors)


h0 = w.start(W3, solved)
t = time.time()
try:
    r = sv.solve(H, start=h0, goal=lambda x: bool(x.path) and x.path[-1].lid == H, heuristic=guide)
except TimeoutError:
    r = 'timeout'
print(f'{time.time() - t:.1f}s, {len(sv.last_search[0]):,} states:',
      solver.flatten(r[0]) if isinstance(r, tuple) else r or 'impossible')
if isinstance(r, tuple):
    h = sv.last_end
    print('entered w3-H with outside', sim.TEMP_CHAR[h.path[-1].t_out])
