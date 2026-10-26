"""Solve a level through given intermediate layouts (sub-goals), stage by stage.

Usage: subgoal.py GAME_DIR LEVEL SECONDS BODY@X,Y[:C] ... [/ BODY@X,Y[:C] ...] ... [--out FILE]
BODY is a body index (see the block list printed first), X,Y its target cell, :C that it must
be cold there. A '/' starts a new stage; every stage must keep what the earlier ones reached.
Each stage is searched from where the previous one ended, guided by the push distance of every
listed body to its target (for a body not yet cold, through a cell where it gets chilled and
that it can be pushed out of again). A last phase continues to solving the level. The joined
plan is replayed from the level's start. Each stage gets SECONDS.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mxw, prune, sim, solver
from show_solution import walkthrough

args = sys.argv[1:]
out_file = None
if '--out' in args:
    i = args.index('--out')
    out_file = args[i + 1]
    del args[i:i + 2]
game, lid, budget, specs = args[0], args[1], float(args[2]), args[3:]
levels = mxw.load_world(game)[0]

stages = [{}]  # per stage: body -> (cell, must be cold)
for spec in specs:
    if spec == '/':
        stages.append({})
        continue
    body, _, rest = spec.partition('@')
    cell, _, temp = rest.partition(':')
    x, y = (int(v) for v in cell.split(','))
    stages[-1][int(body)] = ((x, y), temp.upper() == 'C')
targets = {k: v for st in stages for k, v in st.items()}  # all of them, for the listing

def progress(lid, states, queued, depth):
    print(f'      ... {states:,} states, {queued:,} queued, depth {depth}', flush=True)


sv = solver.Solver(levels, time_budget=budget, h_weight=5, progress=progress)
w = sv.world
m = w.model(lid, frozenset(), sim.NEUTRAL)
tables = sv.pruner.tables(m)
print('blocks:')
for bi, b in enumerate(m.bodies):
    if not b.outside:
        mark = ' <- target ' + str(targets[bi]) if bi in targets else ''
        print(f'  {bi:2} at {m.initial_pos[bi]} {sim.TEMP_CHAR[m.initial_temp[bi]]}'
              f' faces(LDRU) {"".join("SPI"[f] for f in b.faces[0])}{mark}')


def reached(h):
    s = h.top
    return bool(h.path) and all(s.pos[bi] == cell and (not cold or s.temp[bi] == sim.COLD)
                                for bi, (cell, cold) in targets.items())


_push_to = {}


def push_to(target):
    """{cell: fewest pushes to bring a single-cell block from cell to target}, on the static
    level, with the demon needing a free cell behind every push. Cells missing are traps."""
    d = _push_to.get(target)
    if d is None:
        def free(c):
            return m.inside(c) and c not in tables.static
        d, queue = {target: 0}, [target]
        while queue:
            o = queue.pop(0)
            for dx, dy in sim.DIRS:
                prev = (o[0] - dx, o[1] - dy)
                if prev not in d and free(prev) and free((prev[0] - dx, prev[1] - dy)):
                    d[prev] = d[o] + 1
                    queue.append(prev)
        _push_to[target] = d
    return d


def chill_spots(s, bi):
    """Cells where body bi (single cell) would be chilled by a cold body: touching it through
    two conductive faces, or with the demon standing in between (the demon conducts heat but
    stores none, so it can relay cold from a block that cannot be reached otherwise)."""
    faces = m.bodies[bi].faces[0]

    def free(c):
        return m.inside(c) and c not in tables.static
    spots = []
    for j, b in enumerate(m.bodies):
        p = s.pos[j]
        if j == bi or p is None or s.temp[j] != sim.COLD or not b.weight or b.outside:
            continue
        for k, (cx, cy) in enumerate(b.cells):
            c = (p[0] + cx, p[1] + cy)
            for i, (dx, dy) in enumerate(sim.DIRS):
                if b.faces[k][i] == sim.INSULATED:
                    continue
                a = (c[0] + dx, c[1] + dy)
                if not free(a):
                    continue
                # bi itself on a, facing the cold cell with its side OPP[i]
                if faces[sim.OPP[i]] != sim.INSULATED:
                    spots.append(a)
                # the demon on a, bi on a neighbour of a, facing the demon
                for i2, (dx2, dy2) in enumerate(sim.DIRS):
                    a2 = (a[0] + dx2, a[1] + dy2)
                    if a2 != c and free(a2) and faces[sim.OPP[i2]] != sim.INSULATED:
                        spots.append(a2)
    return spots


best_seen = [prune.INF, None]  # lowest guide value reached and its state, for diagnosis


def guide(h):
    v = _guide(h)
    if v < best_seen[0]:
        best_seen[:] = [v, h]
    return v


later = {}  # bodies of the later stages: they must stay able to reach their targets


def _guide(h):
    if not h.path:
        return prune.INF
    s = h.top
    for bi, (cell, _) in later.items():
        if s.pos[bi] is None or s.pos[bi] not in push_to(cell):
            return prune.INF  # pushed where it can never get to its target
    total = 0
    for bi, (cell, cold) in targets.items():
        p = s.pos[bi]
        if p is None:
            return prune.INF
        cost = push_to(cell).get(p, 99)  # 99: a trap, it can never get there
        if cold and s.temp[bi] != sim.COLD:
            # detour past a cell where it gets chilled, which it must also be able to leave
            cost = min((push_to(a).get(p, 99) + push_to(cell).get(a, 99)
                        for a in chill_spots(s, bi)), default=99)
        total += cost
    return total


plan, start = [], None
for n, stage in enumerate(stages, 1):
    targets = {k: v for st in stages[:n] for k, v in st.items()}  # keep the earlier stages
    later = {k: v for st in stages[n:] for k, v in st.items() if k not in targets}
    best_seen[:] = [prune.INF, None]
    sv = solver.Solver(levels, time_budget=budget, h_weight=5, progress=progress)
    t = time.time()
    try:
        r1 = sv.solve(lid, start=start, goal=reached, heuristic=guide)
    except TimeoutError:
        r1 = 'timeout'
    if not isinstance(r1, tuple):
        v, h = best_seen
        print(f'stage {n}: {r1 or "unreachable"}; closest state seen (guide value {v}):')
        if h is not None:
            print(w.current(h).render(h.top))
            for bi, (cell, cold) in targets.items():
                print(f'  body {bi}: at {h.top.pos[bi]}, {sim.TEMP_CHAR[h.top.temp[bi]]}, '
                      f'target {cell}{" cold" if cold else ""}')
        sys.exit(1)
    start = sv.last_end
    plan += r1[0]
    print(f'stage {n}: {time.time() - t:.1f}s, {len(sv.last_search[0]):,} states, {solver.flatten(r1[0])}')
    print(w.current(start).render(start.top))

t = time.time()
sv2 = solver.Solver(levels, time_budget=budget, heuristic='informed', h_weight=3)
r2 = sv2.solve(lid, start=start)
if r2 is None:
    sys.exit('last phase: no way from the layout to the goal')
print(f'last phase: {time.time() - t:.1f}s, {len(sv2.last_search[0]):,} states, {solver.flatten(r2[0])}')

plan += r2[0]
ok = solver.replay(sv, lid, plan)[0]
print(f'joined plan replays: {ok}, {len(solver.flatten(plan))} moves')
if ok and out_file:
    with open(out_file, 'w', encoding='utf-8') as fh:
        walkthrough(sv, lid, plan, out=lambda line: print(line, file=fh))
    print('walkthrough written to', out_file)
