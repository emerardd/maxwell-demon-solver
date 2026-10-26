"""Check the guessed route for w3-H (b35a381c) step by step.

1. inside w3-H (w3 already solved, so the shortcut back to the w3 map is neutral): push the cold
   U one cell right with the demon inside it, walk next to the shortcut and enter it;
2. on the w3 map: search only for getting back into w3-H;
3. back in w3-H: the demon reappears on its start cell, now covered by the U's left arm, which
   is destroyed. Show the state, then search on to solving w3-H.
Usage: try_w3h.py GAME_DIR [seconds per search, default 60]
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mxw, sim, solver
from solve_in_context import context_start

H, W3 = 'b35a381c', '214a0e55'
levels = mxw.load_world(sys.argv[1])[0]
budget = float(sys.argv[2]) if len(sys.argv) > 2 else 60
sv = solver.Solver(levels, time_budget=budget)
w = sv.world
h = context_start(sv, H, frozenset({W3}))
L, D, R, U = range(4)


def show(label, h):
    f = h.path[-1]
    print(f'--- {label}: in {f.lid} (outside {sim.TEMP_CHAR[f.t_out]}), demon {h.top.demon} '
          f'{sim.TEMP_CHAR[h.top.demon_temp]}, path {[x.lid for x in h.path]}')
    if f.lid != W3:
        print(w.current(h).render(h.top))


show('start in w3-H', h)
for d in (R, U, U):
    h = w.step(h, d)
    assert h is not None and h.top.demon_temp != sim.HOT, 'step failed'
show('U pushed right, demon next to the shortcut', h)
h = w.enter(h, L)
assert h is not None, 'cannot enter the shortcut'
show('entered the shortcut', h)

wm = w.model(W3, h.solved, sim.NEUTRAL)
hb = wm.initial_pos[wm.real_block[H]]
doors = [(hb[0] + dx, hb[1] + dy) for dx, dy in sim.DIRS]
tables = sv.pruner.tables(wm)


def back_to_h(x):
    """Walking distance to w3-H's real block on the map; going into any other level is cut."""
    if not x.path or x.path[-1].lid not in (W3, H):
        return float('inf')
    if x.path[-1].lid == H:
        return 0
    dist = tables.walk(wm, x.top.demon)
    return min(dist.get(c, 999) for c in doors)


t = time.time()
r = sv.solve(H, start=h, goal=lambda x: bool(x.path) and x.path[-1].lid == H, heuristic=back_to_h)
assert r is not None, 'no way back into w3-H'
h = sv.last_end
print(f'back into w3-H in {time.time() - t:.1f}s: {solver.flatten(r[0])}')
show('re-entered w3-H', h)
m = w.current(h)
print('glue groups:', {rep: members for rep, (members, _) in m.groups(h.top.glue).items() if len(members) > 1})

t = time.time()
sv2 = solver.Solver(levels, time_budget=budget, heuristic='informed', h_weight=3)
try:
    r = sv2.solve(H, start=h, goal=lambda x: H in x.solved)
    print(f'rest: {time.time() - t:.1f}s:', solver.flatten(r[0]) if r else 'no solution')
except TimeoutError:
    print(f'rest: timeout ({len(sv2.last_search[0]):,} states)')
