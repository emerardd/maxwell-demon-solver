"""List what stands near a level's real block in its parent: level blocks, windows, temperatures.

Usage: near_block.py GAME_DIR LEVEL [radius, default 12] [SOLVED_ID ...]
Positions are printed 1-based (column, row), like where_is.py.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mxw, sim, world

levels = mxw.load_world(sys.argv[1])[0]
lid = sys.argv[2]
radius = int(sys.argv[3]) if len(sys.argv) > 3 else 12
solved = frozenset(sys.argv[4:])
w = world.World(levels)
parent = w.parent[lid]
m = sim.Model(levels[parent], solved)
s = m.initial()
hx, hy = m.initial_pos[m.real_block[lid]]
print(f'{lid} real block in {parent} at column {hx + 1}, row {hy + 1}')


def near(p):
    return abs(p[0] - hx) + abs(p[1] - hy) <= radius


print('level blocks nearby:')
for b, p, t in zip(m.bodies, s.pos, s.temp):
    if b.level_id and near(p):
        faces = ' '.join('SPI'[f] for f in b.faces[0])
        print(f'  column {p[0] + 1:2} row {p[1] + 1:2}  {b.level_id}  {"real" if b.real else "shortcut"}'
              f'  {sim.TEMP_CHAR[t]}  faces(LDRU) {faces}  {"fixed" if b.fixed else "movable"}')
print('other movable blocks nearby:')
for b, p, t in zip(m.bodies, s.pos, s.temp):
    if not b.level_id and not b.fixed and p is not None and near(p):
        faces = ' '.join('SPI'[f] for f in b.faces[0])
        print(f'  column {p[0] + 1:2} row {p[1] + 1:2}  {sim.TEMP_CHAR[t]}  faces(LDRU) {faces}')
occ = m.occupancy(s)
windows = []
for y in range(m.h):
    for x in range(m.w):
        hit = occ.get((x, y))
        if hit and m.bodies[hit[0]].outside and near((x, y)):
            for i, (dx, dy) in enumerate(sim.DIRS):
                n = (x + dx, y + dy)
                if m.inside(n) and n not in occ and m.bodies[hit[0]].faces[hit[1]][i] != sim.INSULATED:
                    windows.append((x + 1, y + 1))
print('windows nearby:', sorted(set(windows)) or 'none')
gp = w.parent.get(parent)
if gp:
    blocks = [o for row in levels[gp].grid for o in row if isinstance(o, mxw.LevelBlock) and o.id == parent]
    for o in blocks:
        print(f'{parent} block in {gp}: flag {o.flag}, unsolved {o.unsolved}, solved {o.solved}')
