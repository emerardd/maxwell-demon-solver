"""Solve a level through given intermediate layouts (sub-goals), stage by stage.

Usage: subgoal.py GAME_DIR LEVEL SECONDS BODY@X,Y[:C] ... [/ BODY@X,Y[:C] ...] ... [--out FILE]
BODY is a body index (see the block list printed first), X,Y its target cell, :C that it must
be cold there. A '/' starts a new stage; every stage must keep what the earlier ones reached.
Each stage is searched from where the previous one ended, guided by the push distance of every
listed body to its target (for a body not yet cold, through a cell where it gets chilled and
that it can be pushed out of again). Bodies needed by later stages must stay able to reach their
targets. A last phase continues to solving the level. The joined plan is replayed from the
level's start. Each stage gets SECONDS.
"""
import os, sys, time
from collections import deque
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mxw, prune, sim, solver


def push_distances(m, static, target, blocked=frozenset()):
    """{cell: fewest pushes to bring a single-cell block from cell to target}, on the static
    level plus the blocked cells, with the demon needing a free cell behind every push.
    Cells missing are traps."""
    def free(c):
        return m.inside(c) and c not in static and c not in blocked
    if not free(target):
        return {}
    d, queue = {target: 0}, deque([target])
    while queue:
        o = queue.popleft()
        for dx, dy in sim.DIRS:
            prev = (o[0] - dx, o[1] - dy)
            if prev not in d and free(prev) and free((prev[0] - dx, prev[1] - dy)):
                d[prev] = d[o] + 1
                queue.append(prev)
    return d


def chill_spots(m, s, static, bi, blocked=frozenset()):
    """Cells where single-cell body bi would be chilled by a cold body: touching it through
    two conductive faces, or with the demon standing in between (the demon conducts heat but
    stores none, so it can relay cold from a block that cannot be reached otherwise)."""
    faces = m.bodies[bi].faces[0]

    def free(c):
        return m.inside(c) and c not in static and c not in blocked
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
                if faces[sim.OPP[i]] != sim.INSULATED:      # bi itself on a
                    spots.append(a)
                for i2, (dx2, dy2) in enumerate(sim.DIRS):   # the demon on a, bi next to it
                    a2 = (a[0] + dx2, a[1] + dy2)
                    if a2 != c and free(a2) and faces[sim.OPP[i2]] != sim.INSULATED:
                        spots.append(a2)
    return spots


class StagedSearch:
    """Reach a list of stages ({body: (cell, must be cold)}) one after another, then the goal."""

    def __init__(self, levels, lid, budget, log=print):
        self.levels, self.lid, self.budget, self.log = levels, lid, budget, log
        self.sv = solver.Solver(levels)
        self.m = self.sv.world.model(lid, frozenset(), sim.NEUTRAL)
        self.tables = self.sv.pruner.tables(self.m)
        self._push = {}

    def push_to(self, cell):
        if cell not in self._push:
            self._push[cell] = push_distances(self.m, self.tables.static, cell)
        return self._push[cell]

    def run(self, stages):
        """Return the joined plan, or None (with the closest state logged) if a stage fails."""
        plan, start = [], None
        for n in range(1, len(stages) + 1):
            self.targets = {k: v for st in stages[:n] for k, v in st.items()}
            self.later = {k: v for st in stages[n:] for k, v in st.items() if k not in self.targets}
            self.best = [prune.INF, None]
            sv = solver.Solver(self.levels, time_budget=self.budget, h_weight=5)
            t = time.time()
            try:
                r = sv.solve(self.lid, start=start, goal=self.reached, heuristic=self.guide)
            except TimeoutError:
                r = 'timeout'
            if not isinstance(r, tuple):
                self._report_failure(n, r)
                return None
            start, plan = sv.last_end, plan + r[0]
            self.log(f'stage {n}: {time.time() - t:.1f}s, {len(sv.last_search[0]):,} states, '
                     f'{solver.flatten(r[0])}')
            self.log(self.m.render(start.top))
        t = time.time()
        sv = solver.Solver(self.levels, time_budget=self.budget, heuristic='informed', h_weight=3)
        r = sv.solve(self.lid, start=start)
        if r is None:
            self.log('last phase: no way from the layout to the goal')
            return None
        self.log(f'last phase: {time.time() - t:.1f}s, {len(sv.last_search[0]):,} states, '
                 f'{solver.flatten(r[0])}')
        return plan + r[0]

    def reached(self, h):
        s = h.top
        return bool(h.path) and all(s.pos[bi] == cell and (not cold or s.temp[bi] == sim.COLD)
                                    for bi, (cell, cold) in self.targets.items())

    def guide(self, h):
        v = self._guide(h)
        if v < self.best[0]:
            self.best = [v, h]
        return v

    def _guide(self, h):
        if not h.path:
            return prune.INF
        s = h.top
        for bi, (cell, _) in self.later.items():
            if s.pos[bi] is None or s.pos[bi] not in self.push_to(cell):
                return prune.INF  # pushed where it can never get to its target
        total = 0
        for bi, (cell, cold) in self.targets.items():
            p = s.pos[bi]
            if p is None:
                return prune.INF
            cost = self.push_to(cell).get(p, 99)  # 99: a trap, it can never get there
            if cold and s.temp[bi] != sim.COLD:
                # detour past a cell where it gets chilled, which it must also be able to leave
                cost = min((self.push_to(a).get(p, 99) + self.push_to(cell).get(a, 99)
                            for a in chill_spots(self.m, s, self.tables.static, bi)), default=99)
            total += cost
        return total

    def _report_failure(self, n, why):
        v, h = self.best
        self.log(f'stage {n}: {why or "unreachable"}; closest state seen (guide value {v}):')
        if h is not None:
            self.log(self.m.render(h.top))
            for bi, (cell, cold) in self.targets.items():
                self.log(f'  body {bi}: at {h.top.pos[bi]}, {sim.TEMP_CHAR[h.top.temp[bi]]}, '
                         f'target {cell}{" cold" if cold else ""}')


def parse_stages(specs):
    stages = [{}]
    for spec in specs:
        if spec == '/':
            stages.append({})
            continue
        body, _, rest = spec.partition('@')
        cell, _, temp = rest.partition(':')
        x, y = (int(v) for v in cell.split(','))
        stages[-1][int(body)] = ((x, y), temp.upper() == 'C')
    return stages


def finish(staged, plan, out_file=None, log=print):
    """Replay the joined plan from the level's start and optionally write a walkthrough."""
    from show_solution import walkthrough
    ok = solver.replay(staged.sv, staged.lid, plan)[0]
    log(f'joined plan replays: {ok}, {len(solver.flatten(plan))} moves')
    if ok and out_file:
        with open(out_file, 'w', encoding='utf-8') as fh:
            walkthrough(staged.sv, staged.lid, plan, out=lambda line: print(line, file=fh))
        log(f'walkthrough written to {out_file}')
    return ok


if __name__ == '__main__':
    args = sys.argv[1:]
    out_file = None
    if '--out' in args:
        i = args.index('--out')
        out_file = args[i + 1]
        del args[i:i + 2]
    game, lid, budget, specs = args[0], args[1], float(args[2]), args[3:]
    levels = mxw.load_world(game)[0]
    stages = parse_stages(specs)
    staged = StagedSearch(levels, lid, budget)
    m = staged.m
    targets = {k: v for st in stages for k, v in st.items()}
    print('blocks:')
    for bi, b in enumerate(m.bodies):
        if not b.outside:
            mark = ' <- target ' + str(targets[bi]) if bi in targets else ''
            print(f'  {bi:2} at {m.initial_pos[bi]} {sim.TEMP_CHAR[m.initial_temp[bi]]}'
                  f' faces(LDRU) {"".join("SPI"[f] for f in b.faces[0])}{mark}')
    plan = staged.run(stages)
    if plan is None or not finish(staged, plan, out_file):
        sys.exit(1)
