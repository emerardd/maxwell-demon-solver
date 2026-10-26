"""Check the "flag 1 = real level block, flag 0 = shortcut" reading against structure.json.

For every level: which levels hold a flag-1 block for it, and does that match its parent in
the level tree. Usage: mxw_real_blocks.py GAME_DIR
"""
import collections, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from mdemon import mxw

levels, structure, _ = mxw.load_world(sys.argv[1])
real = collections.defaultdict(list)  # level id -> [(holder, x, y)] of flag-1 blocks
for lv in levels.values():
    for y, row in enumerate(lv.grid):
        for x, o in enumerate(row):
            if isinstance(o, mxw.LevelBlock) and o.flag == 1:
                real[o.id].append((lv.id, x, y))

parent = {}
kind_of = {}


def walk(node, par):
    for k in ('normalSublevels', 'extraSublevels', 'metaSublevels', 'hintSublevels'):
        for ch in node.get(k, []):
            parent.setdefault(ch['id'], par)
            kind_of.setdefault(ch['id'], k)
            walk(ch, ch['id'])


walk(structure['root'], structure['root']['id'])
counts = collections.Counter()
odd = []
for lid in parent:
    holders = {h for h, _, _ in real.get(lid, [])}
    if not holders:
        counts[f'no real block ({kind_of[lid]})'] += 1
    elif len(real[lid]) > 1:
        counts['several real blocks'] += 1
        odd.append((lid, real[lid], parent[lid]))
    elif holders == {parent[lid]}:
        counts['real block is in the tree parent'] += 1
    else:
        counts['real block elsewhere'] += 1
        odd.append((lid, real[lid], parent[lid]))
for k, v in counts.most_common():
    print(f'{v:5}  {k}')
print('flag-1 blocks for levels outside the tree:', sum(len(v) for k, v in real.items() if k not in parent))
for item in odd[:15]:
    print('  ', item)
