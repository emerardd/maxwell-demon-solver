"""Rule simulator for Maxwell's puzzling demon, world 1-2 mechanics.

Covers: walking, pushing (rigid bodies, chains, fixing pins), sticky faces (w2), heat
exchange (majority rule per conduction component, counted per opaque cell, insulated faces,
demon/transparent conduct but do not count, non-insulated boundary = outside reservoir),
goals and the hot-demon loss. Entering/exiting levels lives in solver.py.

Face codes in .mxw (2 bits per side, order left, down, right, up), verified on the data:
    0 STICKY     sticks to any face it touches; conducts heat. Two cells joined by a pair of
                 sticky faces already in the file are one rigid body from the start.
    1 PLAIN      conducts heat
    2 INSULATED  blocks heat
The demon never sticks. Glued bodies move as one for the rest of the level.
"""
from typing import NamedTuple
import mxw

DIRS = ((-1, 0), (0, 1), (1, 0), (0, -1))  # index == side field order in .mxw
DIR_NAMES = 'LDRU'
OPP = (2, 3, 0, 1)
STICKY, PLAIN, INSULATED = 0, 1, 2
MERGED = STICKY  # a sticky face already touching another sticky face
NEUTRAL, HOT, COLD = 0, 1, -1
TEMP_CODE = {'neutral': NEUTRAL, 'hot': HOT, 'cold': COLD}
TEMP_CHAR = {NEUTRAL: 'n', HOT: 'H', COLD: 'C'}


class Body(NamedTuple):
    cells: tuple        # (dx, dy) offsets from the body's origin cell
    faces: tuple        # per cell, 4 face codes
    fixed: bool
    outside: bool       # fixed boundary wall: stands for the infinite outside
    transparent: bool   # every cell transparent
    weight: int         # heat amount counted by the majority rule
    level_id: str       # '' unless this is a level block
    opaque: tuple       # per cell: stores heat and counts for goals
    real: bool = False  # the level's real block (flag 1), not a shortcut (flag 0)


class State(NamedTuple):
    demon: tuple        # (x, y)
    demon_temp: int
    pos: tuple          # origin per body, None once destroyed
    temp: tuple         # temperature per body
    glue: tuple         # per body, the smallest body index of its glued group
    holes: frozenset = frozenset()  # destroyed cells of fixed bodies (walls), now empty


class Model:
    """Static description of one level for a given set of solved levels and outside temperature.

    weight='cell' counts a multi-cell body once per cell, 'body' counts it once.
    """

    def __init__(self, level, solved=frozenset(), t_out=NEUTRAL, weight='cell'):
        self.level, self.w, self.h, self.t_out = level, level.w, level.h, t_out
        self.goals = [g for g in level.goals if self.inside(g)]
        blocks, starts, level_of, real_cells = {}, [], {}, set()
        for y, row in enumerate(level.grid):
            for x, o in enumerate(row):
                if isinstance(o, mxw.Start):
                    starts.append((x, y))
                elif isinstance(o, mxw.LevelBlock):
                    b = o.solved if o.id in solved else o.unsolved
                    blocks[(x, y)] = b
                    level_of[(x, y)] = o.id
                    if o.flag == 1:
                        real_cells.add((x, y))
                elif isinstance(o, mxw.Block):
                    blocks[(x, y)] = o
                elif o is not None:
                    raise NotImplementedError(f'{type(o).__name__} at {(x, y)} in {level.id}')
        if any(b.temperature == 'retentive' for b in blocks.values()):
            raise NotImplementedError(f'retentive temperature in {level.id}')
        self.starts = starts

        # Bodies: cells joined through pairs of sticky faces form a piece. A piece holding a
        # fixed cell (walls are a mix of pinned and unpinned cells) can never move or come
        # apart, so it is one body. A movable piece is split into one body per cell, joined
        # through the glue grouping instead, so that a single block of it can be destroyed
        # (w3/transition-2). Level blocks stay single.
        parent = {c: c for c in blocks}

        def find(c):
            while parent[c] != c:
                parent[c] = parent[parent[c]]
                c = parent[c]
            return c
        for (x, y), b in blocks.items():
            if (x, y) in level_of:
                continue
            for i in (1, 2):  # down, right: each pair once
                n = (x + DIRS[i][0], y + DIRS[i][1])
                nb = blocks.get(n)
                if nb and n not in level_of and b.side(i) == MERGED and nb.side(OPP[i]) == MERGED:
                    parent[find(n)] = find((x, y))
        pieces = {}
        for c in sorted(blocks, key=lambda c: (c[1], c[0])):
            pieces.setdefault(find(c), []).append(c)
        groups = {}
        for cells in pieces.values():
            if any(blocks[c].fixed for c in cells):
                groups[cells[0]] = cells
            else:
                groups.update({c: [c] for c in cells})
        groups = dict(sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][0])))

        self.bodies, pos, temp = [], [], []
        for cells in groups.values():
            ox, oy = cells[0]
            bs = [blocks[c] for c in cells]
            fixed = any(b.fixed for b in bs)
            opaque = tuple(not b.transparent for b in bs)
            on_border = any(x in (0, self.w - 1) or y in (0, self.h - 1) for x, y in cells)
            lid = level_of.get(cells[0], '')
            heat = sum(TEMP_CODE[b.temperature] for b in bs if not b.transparent)
            self.bodies.append(Body(
                cells=tuple((x - ox, y - oy) for x, y in cells),
                faces=tuple(tuple(b.side(i) for i in range(4)) for b in bs),
                fixed=fixed,
                outside=fixed and on_border and not lid,
                transparent=not any(opaque),
                weight=sum(opaque) if weight == 'cell' else int(any(opaque)),
                level_id=lid,
                opaque=opaque,
                real=cells[0] in real_cells,
            ))
            pos.append((ox, oy))
            temp.append(t_out if self.bodies[-1].outside else (heat > 0) - (heat < 0))
        self.initial_pos, self.initial_temp = tuple(pos), tuple(temp)
        # level id -> body index of its real level block in this level
        self.real_block = {b.level_id: bi for bi, b in enumerate(self.bodies) if b.real}
        # Per body, its sticky faces that point out of the body, as (cell dx, cell dy, side).
        self.sticky = []
        for b in self.bodies:
            own = set(b.cells)
            self.sticky.append(tuple(
                (cx, cy, i) for k, (cx, cy) in enumerate(b.cells) for i in range(4)
                if b.faces[k][i] == STICKY and (cx + DIRS[i][0], cy + DIRS[i][1]) not in own))
        self._members_cache, self._occ_cache = {}, {}
        self.initial_glue = self._glue(self.initial_pos, tuple(range(len(self.bodies))))
        # Per body, its non-insulated faces that point out of the body and into the grid, as
        # (cell dx, cell dy, side index), for heat(). Faces between a body's own cells and
        # faces off the grid edge can never touch anything.
        self.conductive = []
        for b, (ox, oy) in zip(self.bodies, self.initial_pos):
            own = set(b.cells)
            self.conductive.append(tuple(
                (cx, cy, i) for k, (cx, cy) in enumerate(b.cells) for i in range(4)
                if b.faces[k][i] != INSULATED and (cx + DIRS[i][0], cy + DIRS[i][1]) not in own
                and (not b.fixed or self.inside((ox + cx + DIRS[i][0], oy + cy + DIRS[i][1])))))
        self.weights = [b.weight for b in self.bodies]
        self.outside = [b.outside for b in self.bodies]
        # Classes of interchangeable movable bodies (same shape, faces, opacity): swapping two
        # of them gives the same position in the game. Used for symmetry reduction.
        kinds = {}
        for bi, b in enumerate(self.bodies):
            if not b.fixed and not b.level_id:
                kinds.setdefault((b.cells, b.faces, b.opaque), []).append(bi)
        self.sym_classes = [tuple(c) for c in kinds.values() if len(c) > 1]

    def symmetric_key(self, s):
        """s with the positions and temperatures of interchangeable bodies sorted, for
        deduplication. Only bodies glued to nothing take part (glue keys on body indices)."""
        if not self.sym_classes:
            return s
        groups = self.groups(s.glue)
        pos, temp = list(s.pos), list(s.temp)
        for cls in self.sym_classes:
            free = [bi for bi in cls if len(groups[s.glue[bi]][0]) == 1]
            if len(free) < 2:
                continue
            vals = sorted(((s.pos[bi] is None, s.pos[bi] or (0, 0), s.temp[bi]) for bi in free))
            for bi, (gone, p, t) in zip(free, vals):
                pos[bi], temp[bi] = (None if gone else p), t
        return s._replace(pos=tuple(pos), temp=tuple(temp))

    # -- helpers -------------------------------------------------------------------------
    def inside(self, c):
        return 0 <= c[0] < self.w and 0 <= c[1] < self.h

    def initial(self, start=None):
        return State(start or self.starts[0], NEUTRAL, self.initial_pos, self.initial_temp,
                     self.initial_glue)

    def groups(self, glue):
        """{representative: (member bodies, group is immovable)} for a glue tuple."""
        g = self._members_cache.get(glue)
        if g is None:
            members = {}
            for bi, r in enumerate(glue):
                members.setdefault(r, []).append(bi)
            g = {r: (tuple(ms), any(self.bodies[j].fixed for j in ms)) for r, ms in members.items()}
            if len(self._members_cache) > 4096:
                self._members_cache.clear()
            self._members_cache[glue] = g
        return g

    def destroy(self, s, cell):
        """Destroy the block on cell (w3/transition-2). A movable or single-cell body goes away
        and its former group splits where it is now broken; a cell of a larger fixed body (a
        wall) becomes a hole, pinned or not, as seen in the game (w3/path)."""
        bi, _ = self.occupancy(s)[cell]
        if self.bodies[bi].fixed and len(self.bodies[bi].cells) > 1:
            holes = s.holes | {cell}
            return s._replace(holes=holes, glue=self._glue(s.pos, s.glue, holes))
        pos = tuple(None if j == bi else p for j, p in enumerate(s.pos))
        return s._replace(pos=pos, glue=self._glue(pos, tuple(range(len(pos))), s.holes))

    def stuck(self, s, bi):
        """Is body bi glued into a group that can never move?"""
        return self.groups(s.glue)[s.glue[bi]][1]

    def _glue(self, pos, glue, holes=frozenset()):
        """Join groups wherever a sticky face touches another body."""
        parent = list(glue)

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        def join(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
        occ = None
        for bi, faces in enumerate(self.sticky):
            p = pos[bi]
            if not faces or p is None:
                continue
            if occ is None:
                occ = self._occupancy(pos, holes)
            for cx, cy, i in faces:
                hit = occ.get((p[0] + cx + DIRS[i][0], p[1] + cy + DIRS[i][1]))
                if hit is not None:
                    join(bi, hit[0])
        # The faces around a hole point into the wall's own cells, so they are not in
        # self.sticky; a body standing in a hole sticks to the sticky faces around it.
        if holes:
            occ = occ or self._occupancy(pos, holes)
            for hx, hy in holes:
                here = occ.get((hx, hy))
                if here is None:
                    continue
                for i, (dx, dy) in enumerate(DIRS):
                    hit = occ.get((hx + dx, hy + dy))
                    if hit is not None and hit[0] != here[0] and \
                            self.bodies[hit[0]].faces[hit[1]][OPP[i]] == STICKY:
                        join(here[0], hit[0])
        return tuple(find(a) for a in range(len(parent)))

    def occupancy(self, s):
        return self._occupancy(s.pos, s.holes)

    def _occupancy(self, pos, holes=frozenset()):
        """{cell: (body, cell index)}; cached per position tuple and holes. Callers must not
        mutate it."""
        key = (pos, holes)
        occ = self._occ_cache.get(key)
        if occ is None:
            occ = {}
            for bi, p in enumerate(pos):
                if p is not None:
                    for k, (dx, dy) in enumerate(self.bodies[bi].cells):
                        c = (p[0] + dx, p[1] + dy)
                        if c not in holes:
                            occ[c] = (bi, k)
            if len(self._occ_cache) > 50_000:
                self._occ_cache.clear()
            self._occ_cache[key] = occ
        return occ

    # -- rules ---------------------------------------------------------------------------
    def step(self, s, d):
        """One turn: demon moves in direction index d, then heat transfer. None if impossible."""
        if s.demon_temp == HOT:
            return None
        dx, dy = DIRS[d]
        target = (s.demon[0] + dx, s.demon[1] + dy)
        if not self.inside(target):
            return None
        occ = self.occupancy(s)
        pos, glue = s.pos, s.glue
        if target in occ:
            groups = self.groups(glue)
            moving, frontier = set(), [glue[occ[target][0]]]
            while frontier:
                r = frontier.pop()
                if r in moving:
                    continue
                members, immovable = groups[r]
                if immovable:
                    return None
                moving.add(r)
                for bi in members:
                    if pos[bi] is None:
                        continue
                    px, py = pos[bi]
                    for cx, cy in self.bodies[bi].cells:
                        n = (px + cx + dx, py + cy + dy)
                        if not self.inside(n):
                            return None
                        hit = occ.get(n)
                        if hit is not None and glue[hit[0]] not in moving:
                            frontier.append(glue[hit[0]])
            pos = tuple((p[0] + dx, p[1] + dy) if p is not None and glue[bi] in moving else p
                        for bi, p in enumerate(pos))
            glue = self._glue(pos, glue, s.holes)
        return self.heat(s._replace(demon=target, pos=pos, glue=glue))

    def heat(self, s):
        """Heat-transfer phase: each conduction component takes the majority temperature."""
        n = len(self.bodies)
        demon = n
        parent = list(range(n + 1))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        occ = self.occupancy(s)
        bodies, conductive = self.bodies, self.conductive
        for bi, p in enumerate(s.pos):
            if p is None:
                continue
            px, py = p
            for cx, cy, i in conductive[bi]:
                dx, dy = DIRS[i]
                hit = occ.get((px + cx + dx, py + cy + dy))
                if hit is None:
                    continue
                bj, kj = hit
                if bj == bi or bodies[bj].faces[kj][OPP[i]] == INSULATED:
                    continue
                ra, rb = find(bi), find(bj)
                if ra != rb:
                    parent[ra] = rb
        # The demon touches every neighbouring face that is not insulated (also the faces
        # around a hole it stands in, which are not in self.conductive).
        dxy = s.demon
        for i, (dx, dy) in enumerate(DIRS):
            hit = occ.get((dxy[0] + dx, dxy[1] + dy))
            if hit is not None and bodies[hit[0]].faces[hit[1]][OPP[i]] != INSULATED:
                ra, rb = find(hit[0]), find(demon)
                if ra != rb:
                    parent[ra] = rb
        comps = {}
        for a in range(n + 1):
            if a == demon or s.pos[a] is not None:
                comps.setdefault(find(a), []).append(a)
        temp = list(s.temp)
        weights, outside = self.weights, self.outside
        demon_temp = NEUTRAL  # the demon stores no heat of its own
        for members in comps.values():
            if len(members) == 1:
                a = members[0]
                if a < n and bodies[a].transparent:
                    temp[a] = NEUTRAL  # transparent blocks store no heat, like the demon
                continue
            if any(a < n and outside[a] for a in members):
                t = self.t_out
            else:
                bal = sum(weights[a] * temp[a] for a in members if a < n)
                t = (bal > 0) - (bal < 0)
            for a in members:
                if a == demon:
                    demon_temp = t
                elif not outside[a]:
                    temp[a] = t
        return s._replace(demon_temp=demon_temp, temp=tuple(temp))

    def won(self, s):
        if s.demon_temp == HOT or not self.goals:
            return False
        occ = self.occupancy(s)
        for g in self.goals:
            if g in occ:
                bi, k = occ[g]
                b = self.bodies[bi]
                if b.opaque[k] and not b.outside:
                    return True
        return False

    def lost(self, s):
        return s.demon_temp == HOT

    # -- debugging -----------------------------------------------------------------------
    def render(self, s):
        occ = self.occupancy(s)
        rows = []
        for y in range(self.h):
            row = ''
            for x in range(self.w):
                c = (x, y)
                if c == s.demon:
                    row += '@' if s.demon_temp != HOT else '&'
                elif c in occ:
                    bi = occ[c][0]
                    b = self.bodies[bi]
                    if b.outside:
                        row += '#'
                    elif b.level_id:
                        row += 'L'
                    elif b.fixed:
                        row += 'x'
                    elif not b.opaque[occ[c][1]]:
                        row += 't'
                    else:
                        ch = TEMP_CHAR[s.temp[bi]]
                        row += ch.upper() if ch != 'n' else 'o'
                elif c in self.goals:
                    row += '*'
                else:
                    row += '.'
            rows.append(row)
        return '\n'.join(rows)
