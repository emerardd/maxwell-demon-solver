"""A* solver over the nested-level world (world.py) and the in-level rules (sim.py).

The search state is a whole world.HState: solved levels, the path of entered levels, the
current level's state and the saved states of the other levels on the path. A level is solved
when it is added to the solved set, which may happen deep inside the path.

Search works on macro steps, Sokoban style, with a heat-aware twist: the demon conducts heat,
so walking is only folded when it is thermally inert (every conductive neighbour of the cell
has the same, non-hot temperature and the level is already in heat equilibrium). The cells
reachable by inert walking count as one demon position, represented by its smallest cell.
Macro steps are: a push or heat-changing step (after walking), entering a level block, and
quitting the current level.

A plan is a list of steps: a string of direction letters 'L'/'D'/'R'/'U', ('enter', letter)
or ('quit',). Exits after solving a level happen by themselves and are not written down.
"""
from collections import deque
from itertools import count
import heapq, time
from . import prune, sim, world


class Solver:
    """time_budget (seconds) bounds one solve(); progress(level_id, states, queued, depth) is
    called every 20k states if given. h_weight > 1 turns A* into weighted A*: faster, plans no
    longer guaranteed shortest. heuristic='informed' uses prune.Pruner.informed, which is not
    admissible either: it trades plan length for guidance."""

    def __init__(self, levels, max_states=2_000_000, weight='cell', time_budget=None, progress=None,
                 h_weight=1, max_depth=6, heuristic='admissible'):
        self.levels, self.max_states, self.max_depth = levels, max_states, max_depth
        self.time_budget, self.progress, self.h_weight = time_budget, progress, h_weight
        self.heuristic = heuristic
        self.world = world.World(levels, weight, max_depth)
        self.pruner, self.pruned = prune.Pruner(), 0
        self.target = None  # level being solved in the current solve()

    def model(self, lid, solved, t_out):
        return self.world.model(lid, solved, t_out)

    def solve(self, lid, solved=frozenset(), t_out=sim.NEUTRAL, scope=None,
              start=None, goal=None, heuristic=None):
        """Return (plan, solved set afterwards) or None if the level cannot be solved.
        The world state the plan ends in is left in self.last_end.

        scope: start in this level instead (an ancestor of lid on its real chain) and succeed
        once lid is solved; for levels only ever met inside another one.
        Sub-goals: start (a world.HState to begin from instead of the level's start), goal
        (HState -> bool, replaces "lid is solved") and heuristic (HState -> number, replaces
        the built-in one; INF prunes).
        Iterative deepening on the path of entered levels: nested and self-referring levels
        make the state space grow quickly with depth, and most solutions stay shallow."""
        deadline = time.monotonic() + self.time_budget if self.time_budget else float('inf')
        depths = sorted({d for d in (2, 3, 4) if d < self.max_depth} | {self.max_depth})
        self.target = lid
        hooks = (start, goal, heuristic)
        try:
            for depth in depths:
                self.world.max_depth, self.world.depth_hit = depth, False
                result = self._search(lid, solved, t_out, deadline, scope or lid, hooks)
                if result is not None or not self.world.depth_hit:
                    return result  # found, or the limit never cut anything off
            return None
        finally:
            self.world.max_depth = self.max_depth

    def _search(self, lid, solved, t_out, deadline, root, hooks=(None, None, None)):
        w = self.world
        start_h, goal, heuristic = hooks
        h0 = start_h or w.start(root, solved, t_out)
        m0 = w.current(h0)
        self.last_end, self.last_search = h0, ({}, {}, {})
        if goal is None:
            def goal(h):
                return w.finished(h, lid)
            if not m0.starts:
                return None
            if start_h is None and root == lid and m0.won(h0.top):
                return [], solved | {lid}
        elif goal(h0):
            return [], h0.solved
        h_of = heuristic or self._h
        # States are deduplicated by their canonical key; the actual state reached first is
        # kept so plans walk from where the demon really stands. settled[key]: the actual state
        # came out of a heat phase, so it is in heat equilibrium (start, enter and exit states
        # are not and must be checked).
        start = self._key(h0, False)
        prev, actual, depth, settled = {start: None}, {start: h0}, {start: 0}, {start: False}
        self.last_search = (prev, actual, depth)  # kept for analysis after a timeout
        tie = count()
        hv = h_of(h0)
        if hv == prune.INF:
            return None
        queue = [(self.h_weight * hv, 0, next(tie), start)]
        while queue:
            if time.monotonic() > deadline:
                raise TimeoutError(f'time budget used up in {lid} after {len(prev)} states')
            _, _, _, node = heapq.heappop(queue)
            g = depth[node] + 1
            for step, nxt, is_settled in self._successors(actual[node], settled[node]):
                if goal(nxt):
                    prev[('done',)] = (node, step)
                    self.last_end = nxt
                    return self._plan(prev, ('done',)), nxt.solved
                hv = h_of(nxt)
                if hv == prune.INF:
                    self.pruned += 1
                    continue
                key = self._key(nxt, is_settled)
                if key not in prev:
                    prev[key], actual[key], depth[key], settled[key] = (node, step), nxt, g, is_settled
                    if len(prev) > self.max_states:
                        raise RuntimeError(f'state limit reached in {lid}')
                    if self.progress and len(prev) % 20_000 == 0:
                        self.progress(lid, len(prev), len(queue), g)
                    heapq.heappush(queue, (g + self.h_weight * hv, -g, next(tie), key))
        return None

    def _h(self, h):
        """Push-distance bound while in the level being solved (INF marks a dead state).
        Anywhere else at least one more step is needed, and nothing is pruned."""
        if len(h.path) == 1 and h.path[0].lid == self.target:
            m = self.world.current(h)
            if self.heuristic == 'informed':
                return self.pruner.informed(m, h.top)
            return self.pruner.h(m, h.top)
        return 1

    def _key(self, h, settled):
        m = self.world.current(h)
        return h._replace(top=m.symmetric_key(self._canonical(m, h.top, settled)))

    # -- inert walking ---------------------------------------------------------------------
    @staticmethod
    def _in_equilibrium(m, s):
        return m.heat(s._replace(demon=(-9, -9))).temp == s.temp and not m.triggered(s)

    @staticmethod
    def _inert(m, s, occ, c):
        """Would standing on empty cell c leave every temperature unchanged and the demon safe?"""
        seen = None
        if m.pistons:
            touched = m.touching(s, c)
        else:
            touched = []
            for i, (dx, dy) in enumerate(sim.DIRS):
                hit = occ.get((c[0] + dx, c[1] + dy))
                if hit is not None:
                    touched.append((hit[0], m.bodies[hit[0]].faces[hit[1]][sim.OPP[i]]))
        for bi, face in touched:
            if face == sim.INSULATED:
                continue
            t = m.t_out if m.bodies[bi].outside else s.temp[bi]
            if t == sim.HOT or (seen is not None and t != seen):
                return False
            seen = t
        return True

    def _region(self, m, s, occ, fold):
        """Cells reachable by inert walking from s.demon -> {cell: (previous cell, letter)}."""
        region = {s.demon: None}
        if not fold:
            return region
        queue = deque([s.demon])
        while queue:
            c = queue.popleft()
            for d, (dx, dy) in enumerate(sim.DIRS):
                n = (c[0] + dx, c[1] + dy)
                if n not in region and m.inside(n) and n not in occ and self._inert(m, s, occ, n):
                    region[n] = (c, sim.DIR_NAMES[d])
                    queue.append(n)
        return region

    def _canonical(self, m, s, settled=False):
        """Dedup key: the state with the demon moved to the smallest cell of its inert region."""
        if s.demon_temp == sim.HOT or not (settled or self._in_equilibrium(m, s)) or                 (m.pistons and m.triggered(s)):
            return s  # a piston held back by the demon may act once it walks away
        occ = m.occupancy(s)
        if not self._inert(m, s, occ, s.demon):
            return s
        region = self._region(m, s, occ, True)
        return s._replace(demon=min(region, key=lambda c: (c[1], c[0])), demon_temp=sim.NEUTRAL)

    @staticmethod
    def _walk(region, c):
        path = []
        while region[c] is not None:
            c, letter = region[c]
            path.append(letter)
        return ''.join(reversed(path))

    def _successors(self, h, settled=False):
        """Yield (steps, next HState, settled) for every macro step from h."""
        w = self.world
        m, s = w.current(h), h.top
        if s.demon_temp == sim.HOT:
            return
        occ = m.occupancy(s)
        fold = (settled or self._in_equilibrium(m, s)) and self._inert(m, s, occ, s.demon) and             not (m.pistons and m.triggered(s))
        region = self._region(m, s, occ, fold)
        depth = len(h.path)
        for c in region:
            here = h._replace(top=s._replace(demon=c))
            walk = self._walk(region, c)
            lead = [walk] if walk else []
            for d, (dx, dy) in enumerate(sim.DIRS):
                if (c[0] + dx, c[1] + dy) in region:
                    continue
                nxt = w.step(here, d)
                if nxt is not None and not (nxt.path and nxt.top.demon_temp == sim.HOT):
                    same_level = len(nxt.path) == depth and nxt.solved == h.solved
                    yield [walk + sim.DIR_NAMES[d]], nxt, same_level
                try:
                    nxt, steps = w.enter(here, d), [('enter', sim.DIR_NAMES[d])]
                except world.Unenterable:
                    nxt, steps = w.bounce(here, d), [('enter', sim.DIR_NAMES[d]), ('quit',)]
                if nxt is not None:
                    yield lead + steps, nxt, False
        nxt = w.quit(h)
        if nxt is not None:
            yield [('quit',)], nxt, False

    @staticmethod
    def _plan(prev, node):
        chunks = []
        while prev[node] is not None:
            node, step = prev[node]
            chunks.append(step)
        return [s for chunk in reversed(chunks) for s in chunk]


def solve_any(levels, lid, budget, **ctx):
    """Find any plan: the guided search first (fast on heat puzzles, not shortest), then
    shortest-plan A* (better inside nested levels, where the guidance is blind).
    Returns (solver used, plan, solved set) or None; raises TimeoutError if both run out."""
    timed_out = False
    for kw, share in ((dict(heuristic='informed', h_weight=3), 0.5), (dict(), 1.0)):
        sv = Solver(levels, time_budget=budget * share, **kw)
        try:
            r = sv.solve(lid, **ctx)
        except TimeoutError:
            timed_out = True
            continue
        if r is not None:
            return sv, r[0], r[1]
        if not timed_out:
            return None  # searched to the end: no plan
    raise TimeoutError(f'no plan for {lid} within {budget:g}s')


def replay(solver, lid, plan, solved=frozenset(), t_out=sim.NEUTRAL, scope=None):
    """Re-execute a plan step by step through the rules; return (solved, final solved set)."""
    w = solver.world
    h = w.start(scope or lid, solved, t_out)
    steps = list(plan)
    i = 0
    while i < len(steps):
        step = steps[i]
        if not h.path:
            return False, h.solved  # plan continues after the level was already left
        if isinstance(step, str):
            for letter in step:
                h = w.step(h, sim.DIR_NAMES.index(letter))
                if h is None:
                    return False, solved
                if not h.path:
                    break
                if h.top.demon_temp == sim.HOT:
                    return False, h.solved
        elif step[0] == 'enter':
            d = sim.DIR_NAMES.index(step[1])
            try:
                h = w.enter(h, d)
            except world.Unenterable:
                if i + 1 >= len(steps) or steps[i + 1] != ('quit',):
                    return False, solved
                h = w.bounce(h, d)
                i += 1
        elif step[0] == 'quit':
            h = w.quit(h)
        if h is None:
            return False, solved
        i += 1
    return w.finished(h, lid), h.solved


def flatten(plan):
    """Plan as one string: letters for moves, [E<dir>] for entering, [Q] for quitting."""
    out = []
    for step in plan:
        if isinstance(step, str):
            out.append(step)
        elif step[0] == 'enter':
            out.append(f'[E{step[1]}]')
        else:
            out.append('[Q]')
    return ''.join(out)
