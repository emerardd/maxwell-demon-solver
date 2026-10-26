"""How do pistons sit in the grid? For every piston in the game data, by state (extended or
contracted) and direction bits: how often is the neighbouring cell on each side empty in the
file. A side that is always empty for extended pistons is where the movable side sticks out.
Also lists what the slot objects (the block inside a contracted piston) look like.
Usage: piston_geometry.py GAME_DIR
"""
import collections, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from mdemon import mxw
from mdemon.sim import DIRS

levels = mxw.load_world(sys.argv[1])[0]
empty = collections.defaultdict(lambda: [0, 0, 0, 0])
total = collections.Counter()
heads = collections.Counter()
for lv in levels.values():
    for y, row in enumerate(lv.grid):
        for x, o in enumerate(row):
            if not isinstance(o, mxw.Piston):
                continue
            key = ('extended' if o.extended else 'contracted', o.direction)
            total[key] += 1
            for i, (dx, dy) in enumerate(DIRS):
                nx, ny = x + dx, y + dy
                if 0 <= nx < lv.w and 0 <= ny < lv.h and lv.grid[ny][nx] is None:
                    empty[key][i] += 1
            if o.slot is not None:
                h = o.slot
                heads[(type(h).__name__, getattr(h, 'attr', None), getattr(h, 'sides', None))] += 1
print('state, direction bits -> count, and how often the neighbour on each side (L D R U) is empty')
for key in sorted(total):
    n = total[key]
    print(f'  {key[0]:10} dir {key[1]}: {n:4}   ' + '  '.join(f'{"LDRU"[i]} {e / n:4.0%}' for i, e in enumerate(empty[key])))
print('slot objects (type, attr, sides):')
for k, v in heads.most_common(12):
    print(f'  {v:4}  {k[0]} attr {k[1]} sides {k[2]:#04x}' if k[2] is not None else f'  {v:4}  {k}')
