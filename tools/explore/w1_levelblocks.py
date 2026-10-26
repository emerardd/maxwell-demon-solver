"""List w1 levels that contain level blocks, with each block's unsolved/solved state."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from mdemon import catalog, mxw

levels, structure, _ = mxw.load_world(sys.argv[1])
for kind, lid in catalog.world_levels(structure, levels, sys.argv[2] if len(sys.argv) > 2 else 'w1'):
    lv = levels[lid]
    blocks = [(x, y, o) for y, row in enumerate(lv.grid) for x, o in enumerate(row) if isinstance(o, mxw.LevelBlock)]
    if not blocks:
        continue
    print(f'{kind:6} {lid} {lv.w}x{lv.h} goals={lv.goals}')
    for x, y, o in blocks:
        u, s = o.unsolved, o.solved
        print(f'    ({x},{y}) -> {o.id}  unsolved attr={u.attr:x} sides={u.sides:02x}  solved attr={s.attr:x} sides={s.sides:02x}'
              f'  {"(self)" if o.id == lid else ""}{"" if o.id in levels else " (missing file)"}')
