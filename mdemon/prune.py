"""Static push analysis for pruning and the A* heuristic (Sokoban-style dead squares).

For every movable glue group holding an opaque cell, a reverse BFS from the goals over the
*static* level gives the fewest pushes needed to bring one of its opaque cells onto a goal from
each position. The static level keeps only what can never move: boundary walls and fixed
blocks. Everything else is ignored, so the tables are optimistic:
    - other movable blocks are treated as absent;
    - temperature is ignored (a hot block can be cooled or pushed through an insulated one).
That makes "no group can reach a goal" a sound dead-state test and the minimum distance an
admissible heuristic.

Groups change during play: sticky faces glue groups together and a demon appearing on a block
destroys it (w3), which can split a group. A group that still has exactly its initial members
uses its own table. Any other group falls back to per-cell tables of plain distance through free
cells, a lower bound for any shape. When a movable body has a sticky face pointing out of its
initial group, new shapes can be pushed from any member, so the group tables drop the "demon
needs a free cell behind" condition too.

Levels holding a level block get the bound capped at one step: entering it can reset the level,
re-entering this level can move the demon to its start, and solving it can change the block.
"""
from collections import deque
from .sim import DIRS, OPP, INSULATED, HOT, COLD

INF = float('inf')


def static_cells(m):
    cells = set()
    for bi, b in enumerate(m.bodies):
        if b.outside or (b.fixed and not b.level_id):
            ox, oy = m.initial_pos[bi]
            cells.update((ox + cx, oy + cy) for cx, cy in b.cells)
    return cells


def is_candidate(b):
    """Could this body ever be the block standing on the goal?"""
    return not (b.outside or b.transparent or (b.fixed and not b.level_id))


def has_movable_sticky(m):
    """Is there a sticky face that can glue a movable body to something new?"""
    groups = m.groups(m.initial_glue)
    for bi, (b, faces) in enumerate(zip(m.bodies, m.sticky)):
        if not faces or b.fixed:
            continue
        own = set()
        ox, oy = m.initial_pos[bi]
        for j in groups[m.initial_glue[bi]][0]:
            px, py = m.initial_pos[j]
            own.update((px + cx, py + cy) for cx, cy in m.bodies[j].cells)
        if any((ox + cx + DIRS[i][0], oy + cy + DIRS[i][1]) not in own for cx, cy, i in faces):
            return True
    return False


def distances(m, cells, opaque, static, relaxed):
    """{origin: fewest pushes until an opaque cell of the shape is on a goal}."""
    cellset = set(cells)

    def free(c):
        return m.inside(c) and c not in static

    def fits(o):
        return all(free((o[0] + cx, o[1] + cy)) for cx, cy in cells)
    dist, queue = {}, deque()
    for gx, gy in m.goals:
        for (cx, cy), op in zip(cells, opaque):
            o = (gx - cx, gy - cy)
            if op and o not in dist and fits(o):
                dist[o] = 0
                queue.append(o)
    while queue:
        o = queue.popleft()
        for dx, dy in DIRS:
            prev = (o[0] - dx, o[1] - dy)  # the shape stood at prev and was pushed by (dx, dy)
            if prev in dist or not fits(prev):
                continue
            # the demon needs a free cell right behind one of the shape's cells
            if relaxed or any((cx - dx, cy - dy) not in cellset and free((prev[0] + cx - dx, prev[1] + cy - dy))
                              for cx, cy in cells):
                dist[prev] = dist[o] + 1
                queue.append(prev)
    return dist


class Tables:
    def __init__(self, m):
        static = static_cells(m)
        relaxed = has_movable_sticky(m)
        self.group = {}   # rep -> (members, table over the rep's origin)
        for rep, (members, immovable) in m.groups(m.initial_glue).items():
            if immovable:
                continue
            rx, ry = m.initial_pos[rep]
            cells, opaque = [], []
            for j in members:
                px, py = m.initial_pos[j]
                b = m.bodies[j]
                cells += [(px + cx - rx, py + cy - ry) for cx, cy in b.cells]
                opaque += list(b.opaque)
            if any(opaque):
                self.group[rep] = (members, distances(m, cells, opaque, static, relaxed))
        self.cell = [distances(m, b.cells, b.opaque, static, True)
                     if not b.fixed and not b.outside and any(b.opaque) else None
                     for b in m.bodies]
        self.cap = 1 if any(b.level_id for b in m.bodies) else INF
        self.static = static
        self._walk = {}  # cell -> {cell: walking distance on the static level}

    def walk(self, m, a):
        """Distances from cell a through cells that are never blocked by fixed things."""
        d = self._walk.get(a)
        if d is None:
            d, queue = {a: 0}, deque([a])
            while queue:
                c = queue.popleft()
                for dx, dy in DIRS:
                    n = (c[0] + dx, c[1] + dy)
                    if n not in d and m.inside(n) and n not in self.static:
                        d[n] = d[c] + 1
                        queue.append(n)
            self._walk[a] = d
        return d


class Pruner:
    """Caches tables per model and evaluates states against them."""

    def __init__(self):
        self.cache = {}

    def tables(self, m):
        key = id(m)
        if key not in self.cache:
            self.cache[key] = (m, Tables(m))
        return self.cache[key][1]

    def _candidates(self, m, s, t):
        """Yield (distance, table, origin, shape cells, members) per movable group."""
        for rep, (members, immovable) in m.groups(s.glue).items():
            if immovable:
                continue  # glued to something immovable: it never moves again
            initial = t.group.get(rep)
            if initial is not None and initial[0] == members and all(s.pos[j] is not None for j in members):
                d = initial[1].get(s.pos[rep], INF)
                if d < INF:
                    rx, ry = s.pos[rep]
                    shape = [(s.pos[j][0] + cx - rx, s.pos[j][1] + cy - ry)
                             for j in members for cx, cy in m.bodies[j].cells]
                    yield d, initial[1], s.pos[rep], shape, members
            else:
                for j in members:
                    if s.pos[j] is not None and t.cell[j] is not None:
                        d = t.cell[j].get(s.pos[j], INF)
                        if d < INF:
                            yield d, t.cell[j], s.pos[j], list(m.bodies[j].cells), members

    def h(self, m, s):
        """Lower bound on remaining pushes; INF means the state is dead."""
        t = self.tables(m)
        return min([t.cap] + [c[0] for c in self._candidates(m, s, t)])

    OBSTACLE = 3   # informed heuristic: per movable group standing on the candidate's route
    HAZARD = 4     # per hot body that would burn the demon at a push position on the route
    NO_COLD = 10   # a hazard and no cold block anywhere: cooling is not an option
    CHILL = 3      # turning a neutral block cold at a cold source first
    TOO_WEAK = 8   # the carrier holds less cold than the hazard holds heat

    def informed(self, m, s):
        """Not admissible, meant to guide a search that need not find the shortest plan.
        Per candidate: pushes to the goal along its distance table, plus
          - a cost for every other movable group standing on that route (move it first);
          - for every hot body that would touch the demon at a push position on the route
            (the candidate itself included), a cost plus the walking distance from the
            nearest cold block to that hot body, so that bringing cold closer is rewarded;
            for a hot candidate, bringing a glove (a block with an insulated face) behind it
            counts as an alternative to cooling it.
        INF only where h() says the state is dead."""
        t = self.tables(m)
        occ = m.occupancy(s)
        groups = m.groups(s.glue)
        carriers = self._carriers(m, s, groups)
        best = INF
        for d, table, origin, shape, members in self._candidates(m, s, t):
            blockers, hazards, o = set(), set(), origin
            first_behind = None  # where the demon stands for the first push
            while table.get(o, 0) > 0:
                nxt = next((n for n in ((o[0] + dx, o[1] + dy) for dx, dy in DIRS)
                            if table.get(n) == table[o] - 1), None)
                if nxt is None:
                    break
                if first_behind is None:
                    first_behind = (2 * o[0] - nxt[0], 2 * o[1] - nxt[1])
                for cx, cy in shape:
                    hit = occ.get((nxt[0] + cx, nxt[1] + cy))
                    if hit is not None and hit[0] not in members and not m.bodies[hit[0]].fixed:
                        blockers.add(groups[s.glue[hit[0]]][0])
                # after this push the demon stands where the shape's origin was. (Checking
                # the cell behind the shape before the push as well was tried: it misled the
                # search on eadb3d02 and did not crack 4b1153be.)
                step = (nxt[0] - o[0], nxt[1] - o[1])
                hazards |= self._burning(m, s, occ, o, members, step)
                o = nxt
            v = d + self.OBSTACLE * len(blockers)
            done = set()
            for bi in hazards:
                hot_group = groups[s.glue[bi]][0]
                if hot_group in done:
                    continue
                done.add(hot_group)
                cost = self._cooling(m, s, t, hot_group, carriers)
                if hot_group == members and first_behind is not None:
                    # the candidate itself is hot: it can also be pushed through a glove
                    cost = min(cost, self._glove(m, s, t, groups, members, first_behind))
                v += self.HAZARD + cost
            if v < best:
                best = v
        if best == INF and t.cap < INF:
            return 20  # only a level block could help: no guidance, but not dead
        return best

    GLOVE = 2      # setting up a glove: a block with an insulated face pushed in between

    def _glove(self, m, s, t, groups, members, behind):
        """Cost of pushing a hot candidate through a glove: the walking distance from the
        nearest movable, not hot block that has an insulated face to the cell the demon would
        push the candidate from (the glove goes there, the demon pushes the glove)."""
        best = INF
        for rep, (gm, immovable) in groups.items():
            if immovable or gm == members:
                continue
            bodies = [j for j in gm if s.pos[j] is not None]
            if not bodies or any(s.temp[j] == HOT for j in bodies):
                continue
            if not any(f == INSULATED for j in bodies for fs in m.bodies[j].faces for f in fs):
                continue
            for c in self._cells(m, s, bodies):
                dist = t.walk(m, c).get(behind)
                if dist is not None and dist + self.GLOVE < best:
                    best = dist + self.GLOVE
        return best

    @staticmethod
    def _cells(m, s, members):
        return [(s.pos[j][0] + cx, s.pos[j][1] + cy)
                for j in members if s.pos[j] is not None for cx, cy in m.bodies[j].cells]

    def _carriers(self, m, s, groups):
        """(cold sources, cold movable groups, neutral movable groups) for cooling estimates.
        A group entry is (cells, opaque cell count)."""
        sources, cold, neutral = [], [], []
        for rep, (members, immovable) in groups.items():
            bodies = [j for j in members if s.pos[j] is not None and not m.bodies[j].outside]
            if not bodies:
                continue
            temps = {s.temp[j] for j in bodies if m.bodies[j].weight}
            cells = self._cells(m, s, bodies)
            weight = sum(m.bodies[j].weight for j in bodies)
            if COLD in temps:
                sources += cells
                if not immovable:
                    cold.append((cells, weight))
            elif temps == {0} and not immovable and \
                    any(f != INSULATED for j in bodies for fs in m.bodies[j].faces for f in fs):
                neutral.append((cells, weight))
        return sources, cold, neutral

    def _cooling(self, m, s, t, hot_group, carriers):
        """Rough cost of bringing enough cold to a hot group: an existing cold block walked
        over, or a neutral block chilled at a cold source first and then walked over."""
        sources, cold, neutral = carriers
        if not sources:
            return self.NO_COLD
        hot_cells = self._cells(m, s, hot_group)
        need = sum(m.bodies[j].weight for j in hot_group if s.pos[j] is not None)

        def dist(cells_a, cells_b):
            return min((t.walk(m, a).get(b, 50) for a in cells_a for b in cells_b), default=50)
        best = INF
        for cells, weight in cold:
            best = min(best, dist(cells, hot_cells) + (0 if weight >= need else self.TOO_WEAK))
        src_to_hot = dist(sources, hot_cells)
        for cells, weight in neutral:
            best = min(best, dist(cells, sources) + src_to_hot + self.CHILL
                       + (0 if weight >= need else self.TOO_WEAK))
        return best if best < INF else self.NO_COLD

    @staticmethod
    def _burning(m, s, occ, cell, members, shift):
        """Hot bodies whose conductive face would touch a demon standing on cell, with the
        candidate (members) displaced by shift from where it is now."""
        found = set()
        for i, (dx, dy) in enumerate(DIRS):
            n = (cell[0] + dx, cell[1] + dy)
            # the candidate's own cells, at their new place
            for j in members:
                p = s.pos[j]
                if p is None or s.temp[j] != HOT:
                    continue
                b = m.bodies[j]
                for k, (cx, cy) in enumerate(b.cells):
                    if (p[0] + cx + shift[0], p[1] + cy + shift[1]) == n and b.faces[k][OPP[i]] != INSULATED:
                        found.add(j)
            hit = occ.get(n)
            if hit is not None and hit[0] not in members and s.temp[hit[0]] == HOT \
                    and not m.bodies[hit[0]].outside and m.bodies[hit[0]].faces[hit[1]][OPP[i]] != INSULATED:
                found.add(hit[0])
        return found
