"""Check side-code hypotheses: does face code 0 always face another block's code 0 (merged body)?"""
import os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mxw

DIRS = [(-1, 0), (0, 1), (1, 0), (0, -1)]
OPP = [2, 3, 0, 1]

levels, _, _ = mxw.load_world(sys.argv[1])
pairs = collections.Counter(); codes = collections.Counter(); mixed_bodies = 0; zero_to_edge = 0


def blk(o):
    if isinstance(o, mxw.Block):
        return o
    if isinstance(o, mxw.LevelBlock):
        return o.unsolved if isinstance(o.unsolved, mxw.Block) else None
    if isinstance(o, mxw.Piston):
        return o.body
    return None


for lv in levels.values():
    for y, row in enumerate(lv.grid):
        for x, o in enumerate(row):
            b = blk(o)
            if not b:
                continue
            for i, (dx, dy) in enumerate(DIRS):
                f = b.side(i); codes[f] += 1
                nx, ny = x + dx, y + dy
                if not (0 <= nx < lv.w and 0 <= ny < lv.h):
                    if f == 0: zero_to_edge += 1
                    continue
                nb = blk(lv.grid[ny][nx])
                g = nb.side(OPP[i]) if nb else 'empty'
                if f == 0 or g == 0:
                    pairs[(f, g)] += 1
print('face codes', dict(codes))
print('pairs involving code 0', dict(pairs))
print('code-0 faces on grid edge', zero_to_edge)
