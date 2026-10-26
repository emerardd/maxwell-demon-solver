"""Classify every level listed under a hint level's hintSublevels.

A nested entry is "placed" when the parent hint level holds a level block leading to it, and an
"orphan" otherwise. Orphans are printed with their world and a short description.
Usage: mxw_nested_hints.py GAME_DIR
"""
import os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from mdemon import mxw

game = sys.argv[1]
levels, structure, _ = mxw.load_world(game)
KINDS = (('normalSublevels', 'N'), ('extraSublevels', 'X'), ('metaSublevels', 'M'), ('hintSublevels', 'h'))
WORLD_NAMES = {'9a498c50': 'w1', '6c1848b0': 'w2', 'f5087810': 'wA', 'bc35ecc9': 'wB'}
anywhere = collections.defaultdict(set)  # level id -> levels holding a block for it
for lv in levels.values():
    for row in lv.grid:
        for o in row:
            if isinstance(o, mxw.LevelBlock):
                anywhere[o.id].add(lv.id)


def describe(lid):
    lv = levels.get(lid)
    if not lv:
        return 'unparsed'
    objs = collections.Counter(type(o).__name__ for row in lv.grid for o in row if o is not None)
    return f'{lv.w}x{lv.h} goals={lv.goals} {dict(objs)}'


counts = collections.Counter()


def walk(node, path, world):
    for k, tag in KINDS:
        for i, ch in enumerate(node.get(k, []), 1):
            w = WORLD_NAMES.get(ch['id'], world)
            here = path + [f'{tag}{i}']
            if tag == 'h' and path and path[-1].startswith('h'):
                parent = node['id']
                placed = parent in anywhere[ch['id']]
                counts[(w, placed)] += 1
                if not placed:
                    print(f'{w:5} orphan {ch["id"]} under hint {parent}  path={"/".join(here)}')
                    print(f'      {describe(ch["id"])}  blocks for it in: {sorted(anywhere[ch["id"]]) or "none"}')
            walk(ch, here, w)


walk(structure['root'], [], 'w0/root')
print()
for (w, placed), n in sorted(counts.items()):
    print(f'{w:8} {"placed" if placed else "orphan"}: {n}')
