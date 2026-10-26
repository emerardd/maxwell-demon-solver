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

Pistons (w4) are one-cell blocks with a movable side; see docs/rules.md for the model. A turn
is a series of steps (move, then heat); after each step the lowest-numbered hot contracted or
cold extended piston that is not blocked acts, which is the next step's move.
"""
from typing import NamedTuple
from . import mxw

DIRS = ((-1, 0), (0, 1), (1, 0), (0, -1))  # index == side field order in .mxw
DIR_NAMES = 'LDRU'
OPP = (2, 3, 0, 1)
STICKY, PLAIN, INSULATED = 0, 1, 2
MERGED = STICKY  # a sticky face already touching another sticky face
NEUTRAL, HOT, COLD = 0, 1, -1
TEMP_CODE = {'neutral': NEUTRAL, 'hot': HOT, 'cold': COLD}
TEMP_CHAR = {NEUTRAL: 'n', HOT: 'H', COLD: 'C'}
PISTON_SIDE = (3, 2, 1, 0)  # mxw piston direction (up, right, down, left) -> side index
MAX_STEPS = 64              # steps in one turn before it counts as an endless loop


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
    piston: int = -1    # side index of the movable side, for pistons
    priority: int = 0   # pistons: lower numbers act first


class State(NamedTuple):
    demon: tuple        # (x, y)
    demon_temp: int
    pos: tuple          # origin per body, None once destroyed; a piston's content shares its cell
    temp: tuple         # temperature per body
    glue: tuple         # per body, the smallest body index of its glued group
    holes: frozenset = frozenset()  # destroyed cells of fixed bodies (walls), now empty
    pist: tuple = ()    # per piston (Model.pistons order): (extended, content body or -1)


class Model:
    """Static description of one level for a given set of solved levels and outside temperature.

    weight='cell' counts a multi-cell body once per cell, 'body' counts it once.
    """

    def __init__(self, level, solved=frozenset(), t_out=NEUTRAL, weight='cell'):
        self.level, self.w, self.h, self.t_out = level, level.w, level.h, t_out
        self.goals = [g for g in level.goals if self.inside(g)]
        blocks, starts, level_of, real_cells, pistons, slots = {}, [], {}, set(), {}, {}

        def block(o, c, into):
            """Put block or level block o on cell c of into (blocks or slots)."""
            if isinstance(o, mxw.LevelBlock):
                into[c] = o.solved if o.id in solved else o.unsolved
                level_of[(c, into is slots)] = o.id
                if o.flag == 1:
                    real_cells.add((c, into is slots))
            elif isinstance(o, mxw.Block):
                into[c] = o
            else:
                raise NotImplementedError(f'{type(o).__name__} at {c} in {level.id}')
        for y, row in enumerate(level.grid):
            for x, o in enumerate(row):
                if isinstance(o, mxw.Start):
                    starts.append((x, y))
                elif isinstance(o, mxw.Piston):
                    blocks[(x, y)] = o.body
                    pistons[(x, y)] = o
                    if o.slot is not None:
                        block(o.slot, (x, y), slots)
                elif o is not None:
                    block(o, (x, y), blocks)
        level_of = {c: lid for (c, inner), lid in level_of.items() if not inner} | \
            {('slot', c): lid for (c, inner), lid in level_of.items() if inner}
        real_cells = {c if not inner else ('slot', c) for c, inner in real_cells}
        if any(b.temperature == 'retentive' for b in (*blocks.values(), *slots.values())):
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
            if (x, y) in level_of or (x, y) in pistons:
                continue
            for i in (1, 2):  # down, right: each pair once
                n = (x + DIRS[i][0], y + DIRS[i][1])
                nb = blocks.get(n)
                if nb and n not in level_of and n not in pistons and \
                        b.side(i) == MERGED and nb.side(OPP[i]) == MERGED:
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

        # A piston's content is a body of its own, after all others, on the piston's cell.
        groups = list(groups.values()) + [[('slot', c)] for c in sorted(slots, key=lambda c: (c[1], c[0]))]
        self.bodies, pos, temp = [], [], []
        for cells in groups:
            if cells[0][0] == 'slot':
                key, cells = cells[0], [cells[0][1]]
                bs = [slots[cells[0]]]
            else:
                key = cells[0]
                bs = [blocks[c] for c in cells]
            ox, oy = cells[0]
            pis = pistons.get(key) if key[0] != 'slot' else None
            fixed = any(b.fixed for b in bs)
            opaque = tuple(not b.transparent for b in bs)
            on_border = any(x in (0, self.w - 1) or y in (0, self.h - 1) for x, y in cells)
            lid = level_of.get(key, '')
            heat = sum(TEMP_CODE[b.temperature] for b in bs if not b.transparent)
            self.bodies.append(Body(
                cells=tuple((x - ox, y - oy) for x, y in cells),
                faces=tuple(tuple(b.side(i) for i in range(4)) for b in bs),
                fixed=fixed,
                outside=fixed and on_border and not lid and not pis,
                transparent=not any(opaque),
                weight=sum(opaque) if weight == 'cell' else int(any(opaque)),
                level_id=lid,
                opaque=opaque,
                real=key in real_cells,
                piston=PISTON_SIDE[pis.direction] if pis else -1,
                priority=pis.priority if pis else 0,
            ))
            pos.append((ox, oy))
            temp.append(t_out if self.bodies[-1].outside else (heat > 0) - (heat < 0))
        self.initial_pos, self.initial_temp = tuple(pos), tuple(temp)
        # Pistons: body index -> side of the movable side; their order in State.pist; the
        # order in which triggered pistons are tried.
        self.pdir = {bi: b.piston for bi, b in enumerate(self.bodies) if b.piston >= 0}
        self.pistons = sorted(self.pdir)
        self.pindex = {bi: k for k, bi in enumerate(self.pistons)}
        self.by_priority = sorted(self.pistons, key=lambda bi: (self.bodies[bi].priority, bi))
        content_at = {pos[bi]: bi for bi in range(len(pos) - len(slots), len(pos))}
        self.initial_pist = tuple((pistons[pos[bi]].extended, content_at.get(pos[bi], -1))
                                  for bi in self.pistons)
        # level id -> body index of its real level block in this level
        self.real_block = {b.level_id: bi for bi, b in enumerate(self.bodies) if b.real}
        # Per body, its sticky faces that point out of the body, as (cell dx, cell dy, side).
        self.sticky = []
        for b in self.bodies:
            own = set(b.cells)
            self.sticky.append(tuple(
                (cx, cy, i) for k, (cx, cy) in enumerate(b.cells) for i in range(4)
                if b.faces[k][i] == STICKY and (cx + DIRS[i][0], cy + DIRS[i][1]) not in own))
        # Per body, every face that points out of the body, as (cell dx, cell dy, side).
        self.outward = []
        for b in self.bodies:
            own = set(b.cells)
            self.outward.append(tuple(
                (cx, cy, i) for cx, cy in b.cells for i in range(4)
                if (cx + DIRS[i][0], cy + DIRS[i][1]) not in own))
        self._members_cache, self._occ_cache, self._link_cache = {}, {}, {}
        self.initial_glue = self._glue(self.initial_pos, tuple(range(len(self.bodies))),
                                       pist=self.initial_pist)
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
        for bi, b in enumerate(self.bodies if not self.pistons else ()):  # State.pist names bodies
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
                     self.initial_glue, frozenset(), self.initial_pist)

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
        wall) becomes a hole, pinned or not, as seen in the game (w3/path). None for a piston,
        which is not modelled."""
        bi, _ = self.occupancy(s)[cell]
        if bi in self.pdir:
            return None
        if self.bodies[bi].fixed and len(self.bodies[bi].cells) > 1:
            holes = s.holes | {cell}
            return s._replace(holes=holes, glue=self._glue(s.pos, s.glue, holes, s.pist))
        pos = tuple(None if j == bi else p for j, p in enumerate(s.pos))
        return s._replace(pos=pos, glue=self._glue(pos, tuple(range(len(pos))), s.holes, s.pist))

    def stuck(self, s, bi):
        """Is body bi glued into a group that can never move?"""
        return self.groups(s.glue)[s.glue[bi]][1]

    def _glue(self, pos, glue, holes=frozenset(), pist=()):
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
        if self.pistons:
            # A content's sticky side faces stick to the inner walls; a movable side never
            # glues (it links, see _links).
            for a, fa, b, fb, kind in self._contacts(pos, holes, pist):
                if (kind == 'n' and STICKY in (fa, fb)) or (kind == 'w' and fb == STICKY):
                    join(a, b)
            return tuple(find(a) for a in range(len(parent)))
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
        return self._occupancy(s.pos, s.holes, s.pist)

    def _occupancy(self, pos, holes=frozenset(), pist=()):
        """{cell: (body, cell index)}; cached per position tuple, holes and pistons. A
        piston's content is not in it (its cell shows the piston). Callers must not mutate it."""
        key = (pos, holes, pist)
        occ = self._occ_cache.get(key)
        if occ is None:
            occ = {}
            inside = {c for _, c in pist}
            for bi, p in enumerate(pos):
                if p is not None and bi not in inside:
                    for k, (dx, dy) in enumerate(self.bodies[bi].cells):
                        c = (p[0] + dx, p[1] + dy)
                        if c not in holes:
                            occ[c] = (bi, k)
            if len(self._occ_cache) > 50_000:
                self._occ_cache.clear()
            self._occ_cache[key] = occ
        return occ

    # -- pistons --------------------------------------------------------------------------
    def _face_at(self, occ, pist, n, i):
        """The face pointing in direction i of whatever stands on cell n, as (body, face
        code), or None. Through the open front of a contracted piston one touches its content
        (nothing when it is empty)."""
        hit = occ.get(n)
        if hit is None:
            return None
        bi, k = hit
        if self.pdir.get(bi) == i:
            ext, c = pist[self.pindex[bi]]
            if not ext:
                return None if c < 0 else (c, self.bodies[c].faces[0][i])
        return bi, self.bodies[bi].faces[k][i]

    def _contacts(self, pos, holes, pist):
        """Touching faces in a piston level, as (a, face of a, b, face of b, kind). kind 'n':
        ordinary, reported from both sides; 'm': b touches the movable side of piston a; 'w':
        content b touches an inner wall of its piston a (insulated, but sticky faces hold)."""
        occ = self._occupancy(pos, holes, pist)
        holder = {c: P for P, (_, c) in zip(self.pistons, pist) if c >= 0}
        bodies, pdir = self.bodies, self.pdir
        for b, p in enumerate(pos):
            if p is None:
                continue
            P = holder.get(b)
            if P is not None:
                front = pdir[P]
                for i, f in enumerate(bodies[b].faces[0]):
                    if i == front:
                        t = self._face_at(occ, pist, (p[0] + DIRS[i][0], p[1] + DIRS[i][1]), OPP[i])
                        if t is not None:
                            if pdir.get(t[0]) == OPP[i]:
                                yield t[0], t[1], b, f, 'm'
                            else:
                                yield b, f, t[0], t[1], 'n'
                    elif i == OPP[front]:
                        yield P, bodies[P].faces[0][front], b, f, 'm'
                    else:
                        yield P, INSULATED, b, f, 'w'
                continue
            mine = pdir.get(b, -1)
            cells = bodies[b].cells
            for cx, cy, i in self.outward[b]:
                if i == mine and not pist[self.pindex[b]][0]:
                    continue  # recessed movable side: touches the content, if any (above)
                t = self._face_at(occ, pist, (p[0] + cx + DIRS[i][0], p[1] + cy + DIRS[i][1]), OPP[i])
                if t is None or t[0] == b:
                    continue
                f = bodies[b].faces[cells.index((cx, cy))][i]
                if i == mine:
                    yield b, f, t[0], t[1], 'm'
                elif pdir.get(t[0]) == OPP[i] and t[0] not in holder:
                    if pist[self.pindex[t[0]]][0]:
                        yield t[0], t[1], b, f, 'm'
                else:
                    yield b, f, t[0], t[1], 'n'

    def _links(self, pos, holes, pist):
        """{piston: body} for bodies stuck to a movable side (either face sticky): the block in
        front of an extended piston, or the content of a contracted one."""
        key = (pos, holes, pist)
        links = self._link_cache.get(key)
        if links is None:
            links = {a: b for a, fa, b, fb, kind in self._contacts(pos, holes, pist)
                     if kind == 'm' and STICKY in (fa, fb)}
            if len(self._link_cache) > 50_000:
                self._link_cache.clear()
            self._link_cache[key] = links
        return links

    def _passive(self, P, t, delta):
        """Temperature of piston P after being pressed in (+1) or pulled out (-1)."""
        return t if self.bodies[P].transparent else max(COLD, min(HOT, t + delta))

    def _move(self, s, d, seeds, held=(), demon=None, detach=-1, envelop=None):
        """Move seeds one cell in direction d, with everything they push, drag or carry.
        Returns (pos, pist, temp, demon) or None when blocked.

        held: bodies that must stay. demon: for piston moves, 'block' (the demon is in the way)
        or 'push' (pushed along like a block); None for the demon's own push.
        detach: a piston that neither carries its content nor is carried by it. envelop:
        (piston, body) where the piston may move onto the body's cell, taking it in.

        A piston carries its content. A single block moving into the open front of a piston
        that stays goes inside: an extended piston is pressed in (contracts, +1 temperature).
        A content leaving through the front of a piston that stays pulls the movable side out
        if it is stuck to it (extends, -1). A body stuck to a movable side drags the piston
        along, except straight towards or away from it, where the piston gives way."""
        groups, glue, pos, pist = self.groups(s.glue), s.glue, s.pos, s.pist
        occ = self._occupancy(pos, s.holes, pist)
        links = self._links(pos, s.holes, pist)
        content_of = {P: c for P, (_, c) in zip(self.pistons, pist) if c >= 0}
        holder = {c: P for P, c in content_of.items()}
        stuck_to = {b: P for P, b in links.items() if P not in content_of}
        dx, dy = DIRS[d]
        rigid = set()  # pistons that turned out to move: their fronts take no blocks in
        while True:
            moving, entries, exits, stack = set(), {}, {}, list(seeds)
            where = s.demon
            while stack:
                b = stack.pop()
                if b in moving:
                    continue
                members, immovable = groups[glue[b]]
                if immovable:
                    return None
                for m in members:
                    if pos[m] is not None:
                        if m in held:
                            return None
                        moving.add(m)
                for m in members:
                    if pos[m] is None:
                        continue
                    P = holder.get(m)
                    if P is not None:
                        if P == detach:
                            continue
                        if d != self.pdir[P]:
                            stack.append(P)
                            continue  # moves inside its piston: no cell of its own to check
                        exits[m] = P
                    if m in content_of and m != detach:
                        stack.append(content_of[m])
                    if m in links and m not in content_of and d != self.pdir[m] and \
                            envelop != (m, links[m]):
                        stack.append(links[m])
                    if m in stuck_to and d != OPP[self.pdir[stuck_to[m]]]:
                        stack.append(stuck_to[m])
                    px, py = pos[m]
                    for cx, cy in self.bodies[m].cells:
                        n = (px + cx + dx, py + cy + dy)
                        if not self.inside(n):
                            return None
                        if demon and n == s.demon and where == s.demon:
                            if demon == 'block':
                                return None
                            where = (n[0] + dx, n[1] + dy)
                            if not self.inside(where):
                                return None
                            hit = occ.get(where)
                            if hit is not None and hit[0] not in moving:
                                stack.append(hit[0])
                        hit = occ.get(n)
                        if hit is None or hit[0] in moving or envelop == (m, hit[0]):
                            continue
                        h = hit[0]
                        if self.pdir.get(h) == OPP[d] and h not in rigid:
                            if h in content_of:
                                stack.append(content_of[h])
                                continue
                            if len(self.bodies[m].cells) == 1 and m not in self.pdir:
                                if any(P == h and x != m for x, P in entries.items()):
                                    return None
                                entries[m] = h
                                continue
                        stack.append(h)
            late = {P for P in entries.values() if P in moving} - rigid
            if not late:
                break
            rigid |= late
        new_pos = list(pos)
        for m in moving:
            new_pos[m] = (pos[m][0] + dx, pos[m][1] + dy)
        new_pist, temp = list(pist), list(s.temp)
        for c, P in exits.items():
            if P in moving:
                continue
            k = self.pindex[P]
            if links.get(P) == c:
                new_pist[k] = (True, -1)
                temp[P] = self._passive(P, temp[P], -1)
            else:
                new_pist[k] = (False, -1)
        for m, P in entries.items():
            k = self.pindex[P]
            if pist[k][0]:
                temp[P] = self._passive(P, temp[P], +1)
            new_pist[k] = (False, m)
        return tuple(new_pos), tuple(new_pist), tuple(temp), where

    def _envelop(self, s, d, seed):
        """The push of seed in direction d is blocked: a piston pushed towards its front onto
        a block that cannot move slides over it instead and takes it in (extended: pressed in,
        +1 temperature). Seen in the game (w4-3's hint level). (pos, pist, temp, demon) or None."""
        occ = self.occupancy(s)
        for P, (ext, c) in zip(self.pistons, s.pist):
            if self.pdir[P] != d or c >= 0 or s.pos[P] is None:
                continue
            x, y = s.pos[P]
            hit = occ.get((x + DIRS[d][0], y + DIRS[d][1]))
            if hit is None or hit[0] in self.pdir or len(self.bodies[hit[0]].cells) > 1 or \
                    self.bodies[hit[0]].fixed:
                continue
            a = hit[0]
            r = self._move(s, d, [seed], held=(a,), envelop=(P, a))
            if r is None or r[0][P] == s.pos[P]:
                continue
            pos, pist, temp, demon = r
            k = self.pindex[P]
            if ext:
                temp = temp[:P] + (self._passive(P, temp[P], +1),) + temp[P + 1:]
            return pos, pist[:k] + ((False, a),) + pist[k + 1:], temp, demon
        return None

    def _actuate(self, s, P):
        """The move phase of piston P acting (hot contracted: extends; cold extended:
        contracts). The new state before heat transfer, or None when it is blocked.
        Extending pushes the content out, or else moves the piston back off it; contracting
        pulls a block stuck to the movable side in, or else moves the piston over it. Only
        when neither works without pushing the demon is the demon pushed away (seen in the
        game: w4-2 moves the piston back rather than the demon, 1ef673fc and w4-2's first
        press push the demon, the piston being stuck)."""
        k, front = self.pindex[P], self.pdir[P]
        ext, c = s.pist[k]
        if not ext:
            new = (True, -1)
            if c < 0:
                r = s.pos, s.pist, s.temp, s.demon
            else:
                r = next(filter(None, (
                    self._move(s, front, [c], held=(P,), demon=how) or
                    self._move(s, OPP[front], [P], held=(c,), demon=how, detach=P)
                    for how in ('block', 'push'))), None)
        else:
            a = self._links(s.pos, s.holes, s.pist).get(P)
            new = (False, a if a is not None else -1)
            if a is None:
                r = s.pos, s.pist, s.temp, s.demon
            elif len(self.bodies[a].cells) > 1 or a in self.pdir:
                return None
            else:
                r = next(filter(None, (
                    self._move(s, OPP[front], [a], held=(P,), demon=how) or
                    self._move(s, front, [P], held=(a,), demon=how, envelop=(P, a))
                    for how in ('block', 'push'))), None)
        if r is None:
            return None
        pos, pist, temp, demon = r
        pist = pist[:k] + (new,) + pist[k + 1:]
        temp = temp[:P] + (NEUTRAL,) + temp[P + 1:]
        return s._replace(demon=demon, pos=pos, pist=pist, temp=temp,
                          glue=self._glue(pos, s.glue, s.holes, pist))

    def triggered(self, s):
        """Pistons that want to act, in the order they are tried: hot and contracted, or cold
        and extended."""
        return [P for P in self.by_priority
                if s.temp[P] == (COLD if s.pist[self.pindex[P]][0] else HOT)]

    def _turn(self, s):
        """Heat phase, then extra steps while a triggered piston can act. None when the turn
        does not settle within MAX_STEPS steps."""
        for _ in range(MAX_STEPS):
            s = self.heat(s)
            for P in self.triggered(s):
                nxt = self._actuate(s, P)
                if nxt is not None:
                    s = nxt
                    break
            else:
                return s
        return None

    def touching(self, s, cell):
        """[(body, face code)] of the faces next to cell, as the demon standing there meets
        them."""
        occ = self.occupancy(s)
        out = []
        for i, (dx, dy) in enumerate(DIRS):
            n = (cell[0] + dx, cell[1] + dy)
            if self.pistons:
                t = self._face_at(occ, s.pist, n, OPP[i])
            else:
                hit = occ.get(n)
                t = hit and (hit[0], self.bodies[hit[0]].faces[hit[1]][OPP[i]])
            if t:
                out.append(t)
        return out

    def front_body(self, s, cell, d):
        """The body the demon walking in direction d meets on cell: through the open front of
        a contracted piston, its content."""
        hit = self.occupancy(s).get(cell)
        if hit is None:
            return None
        if self.pdir.get(hit[0]) == OPP[d]:
            ext, c = s.pist[self.pindex[hit[0]]]
            if not ext:
                return c if c >= 0 else None
        return hit[0]

    # -- rules ---------------------------------------------------------------------------
    def step(self, s, d):
        """One turn: demon moves in direction index d, then heat transfer (and with pistons,
        any extra steps). None if impossible."""
        if s.demon_temp == HOT:
            return None
        dx, dy = DIRS[d]
        target = (s.demon[0] + dx, s.demon[1] + dy)
        if not self.inside(target):
            return None
        occ = self.occupancy(s)
        if self.pistons:
            if target in occ:
                r = self._move(s, d, [occ[target][0]]) or self._envelop(s, d, occ[target][0])
                if r is None:
                    return None
                pos, pist, temp, _ = r
                s = s._replace(pos=pos, pist=pist, temp=temp,
                               glue=self._glue(pos, s.glue, s.holes, pist))
            return self._turn(s._replace(demon=target))
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
        if self.pistons:
            for a, fa, b, fb, kind in self._contacts(s.pos, s.holes, s.pist):
                if kind != 'w' and fa != INSULATED and fb != INSULATED:
                    ra, rb = find(a), find(b)
                    if ra != rb:
                        parent[ra] = rb
            for t in self.touching(s, s.demon):
                if t[1] != INSULATED:
                    ra, rb = find(t[0]), find(demon)
                    if ra != rb:
                        parent[ra] = rb
            return self._balance(s, find)
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
        return self._balance(s, find)

    def _balance(self, s, find):
        """Give every conduction component (find: body or demon -> component) its majority
        temperature."""
        n = len(self.bodies)
        demon, bodies = n, self.bodies
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
        inside = {P: c for P, (_, c) in zip(self.pistons, s.pist) if c >= 0}
        for g in self.goals:
            if g in occ:
                bi, k = occ[g]
                b = self.bodies[bi]
                if b.opaque[k] and not b.outside:
                    return True
                if bi in inside and self.bodies[inside[bi]].opaque[0]:
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
                    if bi in self.pdir:
                        # extended: arrow of the movable side; contracted: letter, upper case
                        # when it holds a block
                        ext, c = s.pist[self.pindex[bi]]
                        ch = '<v>^'[b.piston] if ext else 'ldru'[b.piston]
                        row += ch.upper() if not ext and c >= 0 else ch
                    elif b.outside:
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
