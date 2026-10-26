"""Summarise mechanics usage across all levels."""
import os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mxw

levels, structure, errors = mxw.load_world(sys.argv[1])
print('parsed', len(levels), 'errors', len(errors), errors)

feat = collections.Counter(); sizes = []; self_ref = 0; max_objs = 0
for lv in levels.values():
    f = set()
    def walk(o):
        if isinstance(o, mxw.Block):
            if not o.fixed:
                f.add('movable'); n_add()
            if o.transparent: f.add('transparent')
            if o.temperature != 'neutral': f.add(o.temperature)
            if any(o.side(i) == 1 for i in range(4)): f.add('side=1')
            if any(o.side(i) == 2 for i in range(4)) and not o.fixed: f.add('side=2 movable')
        elif isinstance(o, mxw.LevelBlock):
            f.add('levelblock'); walk(o.unsolved); walk(o.solved)
        elif isinstance(o, mxw.Piston):
            f.add('piston'); walk(o.body); walk(o.head)
    cnt = [0]
    def n_add(): cnt[0] += 1
    for row in lv.grid:
        for o in row:
            walk(o)
            if isinstance(o, mxw.LevelBlock) and o.id == lv.id: f.add('self-reference')
    starts = sum(isinstance(o, mxw.Start) for row in lv.grid for o in row)
    if starts > 1: f.add('multi-start')
    if len(lv.goals) > 1: f.add('multi-goal')
    feat.update(f); sizes.append(lv.w * lv.h); max_objs = max(max_objs, cnt[0])

for k, v in feat.most_common():
    print(f'{k:18} {v}')
sizes.sort()
print('cells: median', sizes[len(sizes) // 2], 'p90', sizes[int(len(sizes) * .9)], 'max', sizes[-1], '| max movable blocks in one level', max_objs)

def count(node, key):
    c = 0
    for k in ('normalSublevels', 'extraSublevels', 'metaSublevels', 'hintSublevels'):
        for ch in node.get(k, []):
            if k == key: c += 1
            c += count(ch, key)
    return c
root = structure['root']
print({k: count(root, k) for k in ('normalSublevels', 'extraSublevels', 'metaSublevels', 'hintSublevels')}, 'top keys', list(structure))
