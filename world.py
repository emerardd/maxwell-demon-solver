"""Level transitions (w3): entering and exiting levels, with a path of nested levels.

Rules from the w3 tutorial texts:
    exit-1        Exiting (after solving, or by quitting) initialises the states of all levels.
                  The demon comes out of the level block it entered through.
    exit-2        It comes out moving in the direction it last entered that level.
    enter-2       Entering the level you are in keeps its state; the demon reappears at the start.
                  The path does not grow: only the entry direction and outside temperature of
                  the current frame change, so exiting still leaves through the original block
                  but in the direction of the last entry.
    enter-3       Levels left by entering another one keep their state until something exits.
    transition-1  No heat transfer at the moment of entering or exiting.
    transition-2  A block where the demon appears (on entering or exiting) is destroyed.
    transition-3  Entering: the outside temperature is that of the level block entered.
                  Exiting: the outside temperature of the level you are now in becomes neutral.
    goal          Solving a level leaves it at once (an automatic exit).
Assumed here: the demon appears next to the block's initial position (exiting initialises the
parent first), cannot appear inside a boundary wall, and may pick any adjacent level block to
enter (the game enters the one with the lowest number). Entering a level that is lower on the
path (A -> B -> A) adds a frame; max_depth bounds the path so such loops stay finite.
"""
from typing import NamedTuple
import sim


class Frame(NamedTuple):
    lid: str
    t_out: int          # outside temperature of this level while the demon is in it
    dir: int = -1       # direction index the demon last entered this level with
    block: int = -1     # body index of the level block in the frame below


class HState(NamedTuple):
    solved: frozenset
    path: tuple         # Frames; path[0] is the level being solved, path[-1] the current one
    top: sim.State      # state of the current level
    saved: tuple        # ((lid, State), ...) sorted: other levels on the path left mid-way


class Unenterable(Exception):
    """The level exists but its mechanics are not modelled yet."""


class World:
    def __init__(self, levels, weight='cell', max_depth=6):
        self.levels, self.weight, self.max_depth = levels, weight, max_depth
        self.depth_hit = False  # set when max_depth refused an entry
        self.models = {}

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
        m = self.current(h)
        s = h.top
        if s.demon_temp == sim.HOT:
            return None
        cell = (s.demon[0] + sim.DIRS[d][0], s.demon[1] + sim.DIRS[d][1])
        hit = m.occupancy(s).get(cell)
        if hit is None:
            return None
        bi = hit[0]
        lid = m.bodies[bi].level_id
        if not lid or lid not in self.levels:
            return None
        here = h.path[-1].lid
        t_out = s.temp[bi]
        try:
            inner_m = self.model(lid, h.solved, t_out)
        except NotImplementedError as e:
            raise Unenterable(str(e))
        if not inner_m.starts:
            return None
        saved = dict(h.saved)
        if lid == here:                                 # enter-2: same level, same state
            inner = s
            path = h.path[:-1] + (h.path[-1]._replace(t_out=t_out, dir=d),)
        else:
            if len(h.path) >= self.max_depth:
                self.depth_hit = True
                return None
            if not self._is_initial(m, s):
                saved[here] = s._replace(demon=(-1, -1), demon_temp=sim.NEUTRAL)
            inner = saved.pop(lid, None) or inner_m.initial()  # enter-3: kept until an exit
            path = h.path + (Frame(lid, t_out, d, bi),)
        inner = self._appear(inner_m, inner, inner_m.starts[0])
        if inner is None:
            return None
        return HState(h.solved, path, inner, tuple(sorted(saved.items())))

    def bounce(self, h, d):
        """Enter the level block in direction d and quit at once, without simulating the inner
        level. Used for levels whose mechanics are not modelled: the result does not depend on
        them, since quitting initialises everything."""
        m = self.current(h)
        s = h.top
        cell = (s.demon[0] + sim.DIRS[d][0], s.demon[1] + sim.DIRS[d][1])
        hit = m.occupancy(s).get(cell)
        if s.demon_temp == sim.HOT or hit is None or not m.bodies[hit[0]].level_id:
            return None
        bi = hit[0]
        frame = Frame(m.bodies[bi].level_id, s.temp[bi], d, bi)
        return self._exit(h._replace(path=h.path + (frame,)), h.solved)

    def quit(self, h):
        """Leave the current level without solving it. None when it is the level being solved."""
        if len(h.path) < 2 or h.top.demon_temp == sim.HOT:
            return None
        return self._exit(h, h.solved)

    # -- helpers ---------------------------------------------------------------------------
    def _exit(self, h, solved):
        if len(h.path) == 1:  # the level being solved was solved: nothing to come out into
            return HState(solved, (), h.top, ())
        popped, below = h.path[-1], h.path[-2]
        below = below._replace(t_out=sim.NEUTRAL)       # transition-3
        m = self.model(below.lid, solved, below.t_out)
        p = m.initial_pos[popped.block]
        cell = (p[0] + sim.DIRS[popped.dir][0], p[1] + sim.DIRS[popped.dir][1])
        s = self._appear(m, m.initial(), cell)          # exit-1: everything initialised
        if s is None:
            return None
        return HState(solved, h.path[:-2] + (below,), s, ())

    @staticmethod
    def _appear(m, s, cell):
        """Put the demon on cell without heat transfer, destroying a block standing there."""
        if not m.inside(cell):
            return None
        hit = m.occupancy(s).get(cell)
        if hit is not None:
            if m.bodies[hit[0]].outside:
                return None
            s = m.destroy(s, hit[0])
        return s._replace(demon=cell, demon_temp=sim.NEUTRAL)

    @staticmethod
    def _is_initial(m, s):
        return s.pos == m.initial_pos and s.temp == m.initial_temp and s.glue == m.initial_glue
