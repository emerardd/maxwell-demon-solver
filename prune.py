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
from sim import DIRS

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


class Pruner:
    """Caches tables per model and evaluates states against them."""

    def __init__(self):
        self.cache = {}

    def tables(self, m):
        key = id(m)
        if key not in self.cache:
            self.cache[key] = (m, Tables(m))
        return self.cache[key][1]

    def h(self, m, s):
        """Lower bound on remaining pushes; INF means the state is dead."""
        t = self.tables(m)
        best = t.cap
        for rep, (members, immovable) in m.groups(s.glue).items():
            if immovable:
                continue  # glued to something immovable: it never moves again
            initial = t.group.get(rep)
            if initial is not None and initial[0] == members and all(s.pos[j] is not None for j in members):
                d = initial[1].get(s.pos[rep], INF)
            else:
                d = min((t.cell[j].get(s.pos[j], INF) for j in members
                         if s.pos[j] is not None and t.cell[j] is not None), default=INF)
            if d < best:
                best = d
        return best
