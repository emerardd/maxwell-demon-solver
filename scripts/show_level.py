"""Render levels as text grids. Usage: mxw_show.py GAME_DIR [id ...] | --text PREFIX"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mdemon import mxw

TEMP = {'neutral': 'n', 'hot': 'H', 'cold': 'C', 'retentive': 'R'}


def cell(o):
    if o is None:
        return '.' * 6
    if isinstance(o, mxw.Start):
        return '@'.ljust(6)
    if isinstance(o, mxw.Block):
        return f'B{o.attr:x}{o.sides:02x}{TEMP[o.temperature]}'.ljust(6)
    if isinstance(o, mxw.LevelBlock):
        return f'L{o.id[:4]}'.ljust(6)
    if isinstance(o, mxw.Piston):
        # E/C extended or contracted, arrow = movable side, body attr, + = holds a block
        return (f'P{"EC"[not o.extended]}{"^>v<"[o.direction]}{o.body.attr:x}'
                + ('+' if o.slot is not None else '')).ljust(6)
    return '?'.ljust(6)


def show(lv):
    print(f'== {lv.id} {lv.w}x{lv.h} goals={lv.goals} texts={[t[2] for t in lv.texts]}')
    for y, row in enumerate(lv.grid):
        print(f'{y:2} ' + ' '.join(cell(o) for o in row))


if __name__ == '__main__':
    levels, structure, errors = mxw.load_world(sys.argv[1])
    args = sys.argv[2:]
    if args and args[0] == '--text':
        sel = [lv for lv in levels.values() if any(t[2].startswith(args[1]) for t in lv.texts)]
    else:
        sel = [levels[a] for a in args]
    for lv in sel:
        show(lv)
