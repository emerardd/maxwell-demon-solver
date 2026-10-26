"""Level transitions (w3): entering and exiting levels, with a path of nested levels.

Every level has one *real* level block (flag 1 in the file), placed in its *real parent*; all
other blocks for it are shortcuts (flag 0). Checked on the data: all 901 real blocks sit in the
parent that structure.json gives. The path is always the chain of real parents from the level
being solved down to the current level, whichever block was used to get there.

Rules from the w3 tutorial texts (the Chinese texts are the precise ones) and the game:
    exit-1        Exiting (after solving, or by quitting) initialises the states of all levels.
                  The demon comes out into the real parent, next to the real block.
    exit-2        It comes out where it stood when it (last) entered: on the entry side of the
                  real block ("离开关卡的位置和进入时相同"). Tried in the game: whichever block
                  and side the demon enters through, quitting comes out of the real block on
                  the side matching the entry direction.
    enter-1/path  Entering through any block makes the path the real chain down to that level.
                  Levels already on the path keep their frames; levels skipped on the way get
                  the entry direction of the shortcut. So entering a level that is already on
                  the path (the current one included) cuts the path back to it (seen in the
                  game: hint hub -> A -> B, entering A from B and quitting leaves A to the hub).
    enter-2       Entering the level you are in keeps its state; the demon reappears at the start.
    enter-3       Levels left by entering another one keep their state until something exits.
    transition-1  No heat transfer at the moment of entering or exiting.
    transition-2  A block where the demon appears (on entering or exiting) is destroyed. This
                  includes wall cells, pinned ones too (w3/path: the demon comes out into a
                  wall and opens a closed room); a destroyed wall cell becomes a hole.
    transition-3  Entering: the outside temperature is that of the level block entered.
                  Exiting: the outside temperature of the level you are now in becomes neutral.
    goal          Solving a level leaves it at once (an automatic exit).
Assumed here: the demon appears next to the real block's initial position (exiting initialises
the parent first) but never outside the grid, and may pick any adjacent level block to enter
(the game enters the one with the lowest number). Levels whose real chain does not go
through the level being solved cannot be entered (that would leave the puzzle).
"""
from typing import NamedTuple
from . import mxw, sim


class Frame(NamedTuple):
    lid: str
    t_out: int          # outside temperature of this level while the demon is in it
    dir: int = -1       # direction index the demon last entered this level with
    block: int = -1     # body index of this level's real block in the frame below


class HState(NamedTuple):
    solved: frozenset
    path: tuple         # Frames; path[0] is the level being solved, path[-1] the current one
    top: sim.State      # state of the current level
    saved: tuple        # ((lid, State), ...) sorted: other levels left mid-way


class Unenterable(Exception):
    """The level exists but its mechanics are not modelled yet."""


class World:
    def __init__(self, levels, weight='cell', max_depth=6):
        self.levels, self.weight, self.max_depth = levels, weight, max_depth
        self.depth_hit = False  # set when max_depth refused an entry
        self.models = {}
        self.parent = {}        # level id -> level holding its real block
        for lv in levels.values():
            for row in lv.grid:
                for o in row:
                    if isinstance(o, mxw.LevelBlock) and o.flag == 1:
                        self.parent[o.id] = lv.id

    def model(self, lid, solved, t_out):
        key = (lid, solved, t_out)
        if key not in self.models:
            self.models[key] = sim.Model(self.levels[lid], solved, t_out, self.weight)
        return self.models[key]

    def current(self, h):
        f = h.path[-1]
        return self.model(f.lid, h.solved, f.t_out)

    def start(self, lid, solved=frozenset(), t_out=sim.NEUTRAL):
        m = self.model(lid, solved, t_out)
        return HState(solved, (Frame(lid, t_out),), m.initial(), ())

    def finished(self, h, target):
        return target in h.solved

    def chain(self, target, lid):
        """Real parents from target down to lid, or None when lid is not below target."""
        seq = [lid]
        while seq[-1] != target:
            p = self.parent.get(seq[-1])
            if p is None or p in seq:
                return None
            seq.append(p)
        return seq[::-1]

    # -- actions ---------------------------------------------------------------------------
    def step(self, h, d):
        """Move in direction d; solving the current level exits it at once. None if impossible."""
        m = self.current(h)
        s = m.step(h.top, d)
        if s is None:
            return None
        h = h._replace(top=s)
        if m.won(s):
            return self._exit(h, h.solved | {h.path[-1].lid})
        return h

    def enter(self, h, d):
        """Enter the level block next to the demon in direction d. None if there is none.
        Raises Unenterable when that level's mechanics are not modelled."""
        found = self._entry(h, d)
        if found is None:
            return None
        lid, path = found
        m, s = self.current(h), h.top
        try:
            inner_m = self.model(lid, h.solved, path[-1].t_out)
        except NotImplementedError as e:
            raise Unenterable(str(e))
        if not inner_m.starts:
            return None
        here = h.path[-1].lid
        saved = dict(h.saved)
        if lid == here:                                 # enter-2: same level, same state
            inner = s
        else:
            if not self._is_initial(m, s):
                saved[here] = s._replace(demon=(-1, -1), demon_temp=sim.NEUTRAL)
            inner = saved.pop(lid, None) or inner_m.initial()  # enter-3: kept until an exit
        inner = self._appear(inner_m, inner, inner_m.starts[0])
        if inner is None:
            return None
        return HState(h.solved, path, inner, tuple(sorted(saved.items())))

    def bounce(self, h, d):
        """Enter the level block in direction d and quit at once, without simulating the inner
        level. Used for levels whose mechanics are not modelled: the result does not depend on
        them, since quitting initialises everything."""
        found = self._entry(h, d)
        if found is None or len(found[1]) < 2:
            return None
        return self._exit(h._replace(path=found[1]), h.solved)

    def quit(self, h):
        """Leave the current level without solving it. None when it is the level being solved."""
        if len(h.path) < 2 or h.top.demon_temp == sim.HOT:
            return None
        return self._exit(h, h.solved)

    # -- helpers ---------------------------------------------------------------------------
    def _entry(self, h, d):
        """(level id, new path) for entering the block next to the demon in direction d."""
        m, s = self.current(h), h.top
        if s.demon_temp == sim.HOT:
            return None
        cell = (s.demon[0] + sim.DIRS[d][0], s.demon[1] + sim.DIRS[d][1])
        bi = m.front_body(s, cell, d)
        if bi is None:
            return None
        lid = m.bodies[bi].level_id
        if not lid or lid not in self.levels:
            return None
        chain = self.chain(h.path[0].lid, lid)
        if chain is None:
            return None
        if len(chain) > self.max_depth:
            self.depth_hit = True
            return None
        path = []
        try:
            for i, x in enumerate(chain):
                kept = h.path[i] if i < len(h.path) and h.path[i].lid == x else None
                if x == lid:
                    block = kept.block if kept else self._real_block(chain[i - 1], x, h.solved)
                    path.append(Frame(x, s.temp[bi], d, block))
                elif kept:
                    path.append(kept)
                else:                                   # skipped on the way: shortcut's direction
                    path.append(Frame(x, sim.NEUTRAL, d, self._real_block(chain[i - 1], x, h.solved)))
        except NotImplementedError:
            return None  # a level on the way is not modelled: the demon could not come back out
        return lid, tuple(path)

    def _real_block(self, parent, lid, solved):
        return self.model(parent, solved, sim.NEUTRAL).real_block[lid]

    def _exit(self, h, solved):
        if len(h.path) == 1:  # the level being solved was solved: nothing to come out into
            return HState(solved, (), h.top, ())
        popped, below = h.path[-1], h.path[-2]
        below = below._replace(t_out=sim.NEUTRAL)       # transition-3
        m = self.model(below.lid, solved, below.t_out)
        p = m.initial_pos[popped.block]
        cell = (p[0] - sim.DIRS[popped.dir][0], p[1] - sim.DIRS[popped.dir][1])  # exit-2: entry side
        s = self._appear(m, m.initial(), cell)          # exit-1: everything initialised
        if s is None:
            return None
        return HState(solved, h.path[:-2] + (below,), s, ())

    @staticmethod
    def _appear(m, s, cell):
        """Put the demon on cell without heat transfer, destroying a block standing there,
        wall cells included (pinned or not; w3/path needs it)."""
        if not m.inside(cell):
            return None
        if cell in m.occupancy(s):
            s = m.destroy(s, cell)
            if s is None:
                return None
        return s._replace(demon=cell, demon_temp=sim.NEUTRAL)

    @staticmethod
    def _is_initial(m, s):
        return (s.pos == m.initial_pos and s.temp == m.initial_temp and s.glue == m.initial_glue
                and not s.holes and s.pist == m.initial_pist)
