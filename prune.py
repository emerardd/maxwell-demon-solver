"""Static push analysis for pruning and the A* heuristic (Sokoban-style dead squares).

For every body that could ever end up on a goal, a reverse BFS from the goals over the
*static* level gives the fewest pushes needed to bring one of its cells onto a goal from each
origin position. The static level keeps only what can never move: boundary walls and fixed
blocks that are not level blocks. Everything else is ignored, so the tables are optimistic:
    - other movable blocks are treated as absent;
    - temperature is ignored (a hot block can be cooled or pushed through an insulated one);
    - fixed level blocks are treated as movable, since solving their level can free them.
That makes "no candidate body can reach a goal" a sound dead-state test and the minimum
distance an admissible heuristic. Glue changes shapes, so levels with movable sticky bodies
get relaxed tables (see push_tables). A body glued into an immovable group is no longer a
candidate unless it already sits on a goal.
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
    return any(faces and not b.fixed for b, faces in zip(m.bodies, m.sticky))


def push_tables(m):
    """Per body: {origin: fewest pushes until a cell is on a goal}, or None for non-candidates.

    When a movable body has a sticky face, bodies can glue into new shapes that the demon
    pushes from any member, so the "demon needs a free cell behind" condition is dropped and
    the table becomes plain distance through free cells (still a lower bound)."""
    static = static_cells(m)
    relaxed = has_movable_sticky(m)

    def free(c):
        return m.inside(c) and c not in static

    tables = []
    for b in m.bodies:
        if not is_candidate(b):
            tables.append(None)
            continue
        cells, cellset = b.cells, set(b.cells)

        def fits(o):
            return all(free((o[0] + cx, o[1] + cy)) for cx, cy in cells)
        dist, queue = {}, deque()
        for gx, gy in m.goals:
            for k, (cx, cy) in enumerate(cells):
                if not b.opaque[k]:
                    continue  # a transparent cell on the goal does not count
                o = (gx - cx, gy - cy)
                if o not in dist and fits(o):
                    dist[o] = 0
                    queue.append(o)
        while queue:
            o = queue.popleft()
            for dx, dy in DIRS:
                prev = (o[0] - dx, o[1] - dy)  # the body stood at prev and was pushed by (dx, dy)
                if prev in dist or not fits(prev):
                    continue
                # the demon needs a free cell right behind one of the body's cells
                if relaxed or any((cx - dx, cy - dy) not in cellset and free((prev[0] + cx - dx, prev[1] + cy - dy))
                                  for cx, cy in cells):
                    dist[prev] = dist[o] + 1
                    queue.append(prev)
        tables.append(dist)
    return tables


class Pruner:
    """Caches push tables per model and evaluates states against them."""

    def __init__(self):
        self.cache = {}

    def tables(self, m):
        key = id(m)
        if key not in self.cache:
            t = push_tables(m)
            # Entering any level block and coming out again resets every object to its
            # initial position at the cost of one step; account for that shortcut.
            can_reset = any(b.level_id for b in m.bodies)
            init = self._dist(t, m.initial_pos)
            self.cache[key] = (m, t, 1 + init if can_reset else INF)
        return self.cache[key][1:]

    @staticmethod
    def _dist(tables, pos, stuck=None):
        best = INF
        for bi, (t, p) in enumerate(zip(tables, pos)):
            if t is not None and p is not None:
                d = t.get(p, INF)
                if d and stuck is not None and stuck(bi):
                    continue  # glued to something immovable and not on a goal: never will be
                if d < best:
                    best = d
        return best

    def h(self, m, s):
        """Lower bound on remaining pushes; INF means the state is dead."""
        t, via_reset = self.tables(m)
        return min(self._dist(t, s.pos, lambda bi: m.stuck(s, bi)), via_reset)
