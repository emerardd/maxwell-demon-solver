"""Where does the search spend its states? Usage: search_stats.py GAME_DIR LEVEL [states, default 30000]

Runs A* up to a state limit, then reports over the states reached:
    - distinct block layouts (positions, temperatures, glue, holes) and demon positions per layout
    - kind of step that produced each state (push, heat-changing walk, enter, quit)
    - how many states have a hot / cold / neutral candidate block (could stand on the goal)
"""
import collections, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mdemon import mxw, prune, sim, solver

levels = mxw.load_world(sys.argv[1])[0]
lid = sys.argv[2]
limit = int(sys.argv[3]) if len(sys.argv) > 3 else 30_000
sv = solver.Solver(levels, max_states=limit)
try:
    sv.solve(lid)
    print('solved within the limit')
except RuntimeError:
    pass
prev, actual, depth = sv.last_search
w = sv.world
layouts = collections.Counter()
kinds = collections.Counter()
cand = collections.Counter()
for key, h in actual.items():
    s = h.top
    layouts[(tuple(f.lid for f in h.path), s.pos, s.temp, s.glue, s.holes)] += 1
    step = prev[key][1] if prev[key] else None
    if step is None:
        kinds['start'] += 1
    else:
        last = step[-1]
        if isinstance(last, tuple):
            kinds[last[0]] += 1
        else:
            m = w.current(h)
            before = actual[prev[key][0]].top
            kinds['push' if s.pos != before.pos else 'heat-changing walk'] += 1
    m = w.current(h)
    temps = {s.temp[bi] for bi, b in enumerate(m.bodies)
             if s.pos[bi] is not None and prune.is_candidate(b) and not b.level_id}
    cand[tuple(sorted(sim.TEMP_CHAR[t] for t in temps))] += 1

n = len(actual)
print(f'{lid}: {n} states, {len(layouts)} distinct layouts, '
      f'{n / len(layouts):.2f} demon positions per layout, max depth {max(depth.values())}')

# Layouts that only differ by swapping identical blocks are the same position in the game.
def kind(m, bi):
    b = m.bodies[bi]
    return (b.cells, b.faces, b.fixed, b.opaque, b.level_id)

sym = set()
for (path, pos, temp, glue, holes) in layouts:
    m = w.current(next(h for h in actual.values() if tuple(f.lid for f in h.path) == path))
    classes = collections.defaultdict(list)
    rest = []
    for bi, p in enumerate(pos):
        if glue[bi] == bi and all(glue[j] != bi for j in range(len(glue)) if j != bi) and not m.bodies[bi].fixed:
            classes[kind(m, bi)].append((p is None, p, temp[bi]))
        else:
            rest.append((bi, p, temp[bi], glue[bi]))
    sym.add((path, tuple(sorted((k, tuple(sorted(v))) for k, v in classes.items())), tuple(rest), holes))
print(f'  distinct layouts up to swapping identical blocks: {len(sym)} '
      f'({len(layouts) / len(sym):.2f}x fewer)')
print('  most demon positions for one layout:', layouts.most_common(1)[0][1])
print('  produced by:', dict(kinds))
print('  candidate temperatures present (share of states):')
for k, v in cand.most_common(8):
    print(f'    {"".join(k) or "-":6} {v / n:6.1%}')
