"""Print the level tree from structure.json down to a depth, with tutorial text keys."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mdemon import mxw

levels, structure, _ = mxw.load_world(sys.argv[1])
depth = int(sys.argv[2]) if len(sys.argv) > 2 else 2
KINDS = (('normalSublevels', 'N'), ('extraSublevels', 'X'), ('metaSublevels', 'M'), ('hintSublevels', 'h'))


def walk(node, d, kind):
    lv = levels.get(node['id'])
    info = f'{lv.w}x{lv.h} goals={lv.goals}' if lv else 'unparsed'
    keys = sorted({t[2].split('/')[0] for t in lv.texts}) if lv else []
    print('  ' * d + f'[{kind}] {node["id"]} {info} {keys}')
    if d < depth:
        for k, tag in KINDS:
            for ch in node.get(k, []):
                walk(ch, d + 1, tag)


def find(node, lid):
    if node['id'] == lid:
        return node
    for k, _ in KINDS:
        for ch in node.get(k, []):
            if r := find(ch, lid):
                return r


start = find(structure['root'], sys.argv[3]) if len(sys.argv) > 3 else structure['root']
walk(start, 0, 'root')
