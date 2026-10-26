"""A* solver over sim.Model, with entering level blocks.

Enter semantics (w1/w3 texts): entering a level block from direction d sets the inner outside
temperature to the block's temperature. Exiting (after solving, or by quitting) initialises
all levels; the demon comes out of the level block continuing in direction d. Assumed here:
it appears next to the block's *initial* position, destroying a movable block standing there.

Search works on pushes, Sokoban style, with a heat-aware twist: the demon conducts heat, so
walking is only folded when it is thermally inert (every conductive neighbour of the cell has
the same, non-hot temperature and the level is already in heat equilibrium). The cells
reachable by inert walking count as one demon position, represented by its smallest cell.

A plan is a list of steps: a string of direction letters 'L'/'D'/'R'/'U', or
('enter', direction letter, level_id, inner plan or None when quitting).
"""
from collections import deque
from itertools import count
import heapq, time
import prune, sim


class Solver:
    """time_budget (seconds) bounds one top-level solve() including nested levels;
    progress(level_id, states, queued, depth) is called every 20k states if given.
    h_weight > 1 turns A* into weighted A*: faster, plans no longer guaranteed shortest."""

    def __init__(self, levels, max_states=2_000_000, weight='cell', time_budget=None, progress=None,
                 h_weight=1):
        self.levels, self.max_states, self.weight = levels, max_states, weight
        self.time_budget, self.progress, self.h_weight = time_budget, progress, h_weight
        self.deadline = float('inf')
        self.models, self.memo = {}, {}
        self.pruner, self.pruned = prune.Pruner(), 0

    def model(self, lid, solved, t_out):
        key = (lid, solved, t_out)
        if key not in self.models:
            self.models[key] = sim.Model(self.levels[lid], solved, t_out, self.weight)
        return self.models[key]

    def solve(self, lid, solved=frozenset(), t_out=sim.NEUTRAL, stack=()):
        """Return (plan, solved_after) or None."""
        key = (lid, solved, t_out)
        if key in self.memo:
            return self.memo[key]
        if lid in stack:  # recursion into a level already being solved: not handled in w1
            return None
        top = not stack
        if top and self.time_budget:
            self.deadline = time.monotonic() + self.time_budget
        self.memo[key] = None  # guard against cycles through the memo
        try:
            result = self._bfs(lid, solved, t_out, stack + (lid,))
        except (TimeoutError, RuntimeError):
            del self.memo[key]  # an aborted search proves nothing
            raise
        finally:
            if top:
                self.deadline = float('inf')
        self.memo[key] = result
        return result

    def _bfs(self, lid, solved, t_out, stack):
        m0 = self.model(lid, solved, t_out)
        if not m0.starts:
            return None
        s0 = m0.initial()
        if m0.won(s0):
            return [], solved
        # A* over macro steps (one push / heat-changing step / level entry each). States are
        # deduplicated by their canonical key; the actual state reached first is kept so plans
        # walk from where the demon really stands.
        # settled[key]: the actual state came out of a heat phase, so it is already in heat
        # equilibrium (initial and post-exit states are not and must be checked).
        start = (solved, self._canonical(m0, s0))
        prev, actual, depth, settled = {start: None}, {start: s0}, {start: 0}, {start: False}
        tie = count()
        h0 = self._h(m0, s0)
        if h0 == prune.INF:
            return None
        queue = [(self.h_weight * h0, 0, next(tie), start)]
        while queue:
            if time.monotonic() > self.deadline:
                raise TimeoutError(f'time budget used up in {lid} after {len(prev)} states')
            _, _, _, node = heapq.heappop(queue)
            node_solved = node[0]
            m = self.model(lid, node_solved, t_out)
            g = depth[node] + 1
            for step, (new_solved, nxt), won, is_settled in self._successors(
                    lid, m, node_solved, actual[node], t_out, stack, settled[node]):
                m2 = self.model(lid, new_solved, t_out)
                key = (new_solved, nxt if won else self._canonical(m2, nxt, is_settled))
                h = 0 if won else self._h(m2, nxt)
                if h == prune.INF:
                    self.pruned += 1
                    continue
                if key not in prev:
                    prev[key], actual[key], depth[key], settled[key] = (node, step), nxt, g, is_settled
                    if won:
                        return self._plan(prev, key), new_solved
                    if len(prev) > self.max_states:
                        raise RuntimeError(f'state limit reached in {lid}')
                    if self.progress and len(prev) % 20_000 == 0:
                        self.progress(lid, len(prev), len(queue), g)
                    heapq.heappush(queue, (g + self.h_weight * h, -g, next(tie), key))
        return None

    def _h(self, m, s):
        """Push-distance lower bound from prune.py; INF marks a dead state."""
        return self.pruner.h(m, s)

    # -- inert walking ---------------------------------------------------------------------
    @staticmethod
    def _in_equilibrium(m, s):
        return m.heat(s._replace(demon=(-9, -9))).temp == s.temp

    @staticmethod
    def _inert(m, s, occ, c):
        """Would standing on empty cell c leave every temperature unchanged and the demon safe?"""
        seen = None
        for i, (dx, dy) in enumerate(sim.DIRS):
            n = (c[0] + dx, c[1] + dy)
            if n in occ:
                bi, k = occ[n]
                body = m.bodies[bi]
                if body.faces[k][sim.OPP[i]] == sim.INSULATED:
                    continue
                t = m.t_out if body.outside else s.temp[bi]
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
        if s.demon_temp == sim.HOT or not (settled or self._in_equilibrium(m, s)):
            return s
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

    def _successors(self, lid, m, solved, s, t_out, stack, settled=False):
        """Yield (step, next node, won, settled) for every push, heat-changing step or entry."""
        if s.demon_temp == sim.HOT:
            return
        occ = m.occupancy(s)
        fold = (settled or self._in_equilibrium(m, s)) and self._inert(m, s, occ, s.demon)
        region = self._region(m, s, occ, fold)
        for c in region:
            here = s._replace(demon=c)
            walk = self._walk(region, c)
            for d, (dx, dy) in enumerate(sim.DIRS):
                target = (c[0] + dx, c[1] + dy)
                if target in region:
                    continue
                nxt = m.step(here, d)
                if nxt is not None and not m.lost(nxt):
                    yield [walk + sim.DIR_NAMES[d]], (solved, nxt), m.won(nxt), True
                if target not in occ:
                    continue
                bi = occ[target][0]
                inner = m.bodies[bi].level_id
                if not inner or inner not in self.levels:
                    continue
                options = [(None, solved)]
                try:
                    sub = self.solve(inner, solved, s.temp[bi], stack)
                except NotImplementedError:
                    sub = None  # mechanics not modelled yet: the level can still be entered and quit
                if sub:
                    options.append((sub[0], sub[1] | {inner}))
                for inner_plan, new_solved in options:
                    after = self._exit_state(lid, new_solved, t_out, bi, d)
                    if after is not None:
                        steps = [w for w in (walk,) if w] + [('enter', sim.DIR_NAMES[d], inner, inner_plan)]
                        yield steps, (new_solved, after), False, False

    def _exit_state(self, lid, solved, t_out, bi, d):
        m = self.model(lid, solved, t_out)
        p = m.initial_pos[bi]
        out = (p[0] + sim.DIRS[d][0], p[1] + sim.DIRS[d][1])
        if not m.inside(out):
            return None
        s = m.initial()
        occ = m.occupancy(s)
        pos = list(s.pos)
        if out in occ:
            bj = occ[out][0]
            if m.bodies[bj].outside:
                return None
            pos[bj] = None  # destroyed by the demon appearing there
        return sim.State(out, sim.NEUTRAL, tuple(pos), s.temp, s.glue)

    @staticmethod
    def _plan(prev, node):
        chunks = []
        while prev[node] is not None:
            node, step = prev[node]
            chunks.append(step)
        return [s for chunk in reversed(chunks) for s in chunk]


def replay(solver, lid, plan, solved=frozenset(), t_out=sim.NEUTRAL):
    """Re-execute a plan step by step through the rules; return (won, final solved set)."""
    m = solver.model(lid, solved, t_out)
    s = m.initial()
    for step in plan:
        if isinstance(step, str):
            for letter in step:
                s = m.step(s, sim.DIR_NAMES.index(letter))
                if s is None or m.lost(s):
                    return False, solved
            continue
        _, dname, inner, inner_plan = step
        d = sim.DIR_NAMES.index(dname)
        dx, dy = sim.DIRS[d]
        occ = m.occupancy(s)
        c = (s.demon[0] + dx, s.demon[1] + dy)
        if c not in occ or m.bodies[occ[c][0]].level_id != inner:
            return False, solved
        bi = occ[c][0]
        if inner_plan is not None:
            ok, solved = replay(solver, inner, inner_plan, solved, s.temp[bi])
            if not ok:
                return False, solved
            solved = solved | {inner}
        m = solver.model(lid, solved, t_out)
        s = solver._exit_state(lid, solved, t_out, bi, d)
        if s is None:
            return False, solved
    return m.won(s), solved


def flatten(plan):
    out = []
    for step in plan:
        if isinstance(step, str):
            out.append(step)
        else:
            _, d, inner, inner_plan = step
            out.append(f'E{d}[{inner}:{flatten(inner_plan) if inner_plan else "quit"}]')
    return ''.join(out)
