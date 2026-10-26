"""Render a level with the cells the demon can walk to marked '+', for a given solved set.

Usage: map_reach.py GAME_DIR LEVEL [SOLVED_ID ...]    ('normals:WORLD' adds a world's numbered levels)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mdemon import catalog, mxw, sim

levels, structure, _ = mxw.load_world(sys.argv[1])
lid = sys.argv[2]
solved = set()
for a in sys.argv[3:]:
    if a.startswith('normals:'):
        node = catalog.find(structure['root'], catalog.WORLDS.get(a[8:], a[8:]))
        solved |= {ch['id'] for ch in node.get('normalSublevels', [])}
    else:
        solved.add(a)
m = sim.Model(levels[lid], frozenset(solved))
s = m.initial()
occ = m.occupancy(s)
seen, stack = {s.demon}, [s.demon]
while stack:
    c = stack.pop()
    for dx, dy in sim.DIRS:
        n = (c[0] + dx, c[1] + dy)
        if n not in seen and m.inside(n) and n not in occ:
            seen.add(n)
            stack.append(n)
rows = [list(r) for r in m.render(s).split('\n')]
for x, y in seen:
    if rows[y][x] == '.':
        rows[y][x] = '+'
for i, r in enumerate(rows, 1):
    print(f'{i:2} {"".join(r)}')
print('level blocks next to the walkable area:')
for (x, y) in sorted(seen):
    for dx, dy in sim.DIRS:
        hit = occ.get((x + dx, y + dy))
        if hit and m.bodies[hit[0]].level_id:
            b = m.bodies[hit[0]]
            print(f'  column {x + dx + 1} row {y + dy + 1}: {b.level_id} {"real" if b.real else "shortcut"}'
                  f' {sim.TEMP_CHAR[s.temp[hit[0]]]} {"fixed" if b.fixed else "movable"}'
                  f'{" solved" if b.level_id in solved else ""}')
