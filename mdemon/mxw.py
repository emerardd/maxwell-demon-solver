"""Parser for Maxwell's puzzling demon level files (world/*.mxw).

Reverse-engineered from the shipped data; all 1153 files parse with no leftover bytes (the
length of tag 05 comes from MatttNguyen/mpd-leditor, a level editor for the game).
Fields marked (?) are hypotheses that still need checking against the game.

File layout
    u8 W, u8 H
    W*H cell objects, row-major
    trailer:
        u8 n_goals, then n_goals * (i8 x, i8 y)      goals may lie outside the grid (e.g. -1)
        repeated { 02, i8 x, i8 y, cstr text_key }   tutorial text, key into languages/*.json "hint"
        00

Object (tag byte first)
    00                      empty
    01                      demon start point
    02 attr sides           block
    03 flag cstr id A B     level block; A/B = block objects for unsolved/solved state
    04 st body prio [head]  piston; head object present only when st bit0 == 0 (expanded)
    05 attr sides x y       piston head variant with two extra bytes (meaning unknown)

attr bits (?)   bit0 fixed pin, bit1 stores heat (0 = transparent), bit2 hot, bit3 cold,
                bit2+bit3 = 4th ("retentive") temperature
sides           2 bits per side, field0=left, 1=down, 2=right, 3=up;
                value 0 plain, 1 sticky (?), 2 insulated (?)
piston st (?)   bit0 contracted, bits1-2 facing direction
"""
from dataclasses import dataclass, field
import json, os

SIDES = ('left', 'down', 'right', 'up')


@dataclass
class Block:
    attr: int
    sides: int

    @property
    def fixed(self): return bool(self.attr & 1)
    @property
    def transparent(self): return not self.attr & 2
    @property
    def temperature(self):
        return {0: 'neutral', 4: 'hot', 8: 'cold', 12: 'retentive'}[self.attr & 12]
    def side(self, i): return (self.sides >> (2 * i)) & 3


@dataclass
class Start:
    pass


@dataclass
class LevelBlock:
    flag: int
    id: str
    unsolved: object
    solved: object


@dataclass
class Piston:
    state: int
    body: object
    priority: int
    head: object = None

    @property
    def contracted(self): return bool(self.state & 1)
    @property
    def direction(self): return (self.state >> 1) & 3


@dataclass
class Head:
    attr: int
    sides: int
    extra: tuple  # two bytes, meaning unknown


@dataclass
class Level:
    id: str
    w: int
    h: int
    grid: list
    goals: list
    texts: list = field(default_factory=list)


class FormatError(Exception):
    pass


def parse(buf, level_id=''):
    p = 0

    def u8():
        nonlocal p
        if p >= len(buf):
            raise FormatError('unexpected end of file')
        p += 1
        return buf[p - 1]

    def i8():
        b = u8()
        return b - 256 if b >= 128 else b

    def cstr():
        nonlocal p
        end = buf.index(0, p)
        s = buf[p:end].decode('utf-8')
        p = end + 1
        return s

    def obj():
        tag = u8()
        if tag == 0:
            return None
        if tag == 1:
            return Start()
        if tag == 2:
            return Block(u8(), u8())
        if tag == 3:
            flag = u8()
            lid = cstr()
            return LevelBlock(flag, lid, obj(), obj())
        if tag == 4:
            st = u8()
            body = obj()
            prio = u8()
            head = obj() if not st & 1 else None
            return Piston(st, body, prio, head)
        if tag == 5:  # 5 bytes long, as in MatttNguyen/mpd-leditor's level_dat.gd
            return Head(u8(), u8(), (u8(), u8()))
        raise FormatError(f'unknown tag {tag:#x} at offset {p - 1}')

    w, h = u8(), u8()
    grid = [[obj() for _ in range(w)] for _ in range(h)]
    goals = [(i8(), i8()) for _ in range(u8())]
    texts = []
    while (t := u8()) != 0:
        if t != 2:
            raise FormatError(f'unknown trailer record {t:#x} at offset {p - 1}')
        texts.append((i8(), i8(), cstr()))
    if p != len(buf):
        raise FormatError(f'{len(buf) - p} trailing bytes')
    return Level(level_id, w, h, grid, goals, texts)


def load_world(game_dir):
    """Return ({id: Level}, structure_json, {id: error})."""
    wdir = os.path.join(game_dir, 'world')
    levels, errors = {}, {}
    for f in sorted(os.listdir(wdir)):
        if f.endswith('.mxw'):
            lid = f[:-4]
            with open(os.path.join(wdir, f), 'rb') as fh:
                buf = fh.read()
            try:
                levels[lid] = parse(buf, lid)
            except FormatError as e:
                errors[lid] = str(e)
    with open(os.path.join(wdir, 'structure.json'), encoding='utf-8-sig') as fh:
        structure = json.load(fh)
    return levels, structure, errors
