"""Describe how to find a level in the game, in terms a player can see.

Usage: where_is.py GAME_DIR LEVEL [LEVEL ...]
For each level: the chain of levels leading to it (world, numbered / lettered level, hint
level), where its level block sits on the parent's map (row and column counted from 1 at the
top left), the tutorial texts placed near that block, and the level's own map.
Level numbering follows the order in structure.json (normal 1, 2, ...; extra A, B, ...), which
is assumed to match the game.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mdemon import mxw, sim

WORLDS = {'c8bcffce': 'w0', '9a498c50': 'w1', '6c1848b0': 'w2', '214a0e55': 'w3',
          'f5087810': 'wA', 'bc35ecc9': 'wB'}
GREEK = 'αβγδεζηθικλμνξοπρστυφχψω'

game = sys.argv[1]
levels, structure, _ = mxw.load_world(game)
with open(os.path.join(game, 'languages', 'zh-CN.json'), encoding='utf-8-sig') as fh:
    zh = json.load(fh)['hint']


def text(key):
    node = zh
    for part in key.split('/'):
        node = node.get(part, {}) if isinstance(node, dict) else {}
    return node if isinstance(node, str) else key


def label(kind, i, lid):
    if lid in WORLDS:
        return f'世界 {WORLDS[lid]}'
    return {'normalSublevels': f'第 {i} 关', 'extraSublevels': f'额外关 {chr(64 + i)}',
            'metaSublevels': f'元关卡 {GREEK[i - 1]}', 'hintSublevels': '提示关'}[kind]


def chains(node, path):
    yield node['id'], path
    for kind in ('normalSublevels', 'extraSublevels', 'metaSublevels', 'hintSublevels'):
        for i, ch in enumerate(node.get(kind, []), 1):
            yield from chains(ch, path + [(kind, i, ch['id'])])


def block_in(parent_id, lid):
    """The real level block (flag 1) for lid in the parent, else any block for it."""
    parent = levels.get(parent_id)
    if not parent:
        return None
    found = [(o.flag, x, y) for y, row in enumerate(parent.grid) for x, o in enumerate(row)
             if isinstance(o, mxw.LevelBlock) and o.id == lid]
    if not found:
        return None
    _, x, y = max(found)
    return parent, x, y


where = {}
for lid, path in chains(structure['root'], []):
    where.setdefault(lid, path)

for lid in sys.argv[2:]:
    path = where.get(lid)
    print(f'===== {lid}')
    if path is None:
        print('不在关卡树里')
        continue
    steps, parent_id = [], structure['root']['id']
    for kind, i, cid in path:
        hit = block_in(parent_id, cid)
        if kind == 'hintSublevels' and not hit:
            steps.append('在上一关里按 H，进入它的提示关')
        else:
            where_txt = ''
            if hit:
                parent, x, y = hit
                near = sorted(parent.texts, key=lambda t: abs(t[0] - x) + abs(t[1] - y))
                tip = f'，旁边的提示：「{text(near[0][2])}」' if near and abs(near[0][0] - x) + abs(near[0][1] - y) <= 2 else ''
                where_txt = f'（关卡块在第 {y + 1} 行第 {x + 1} 列{tip}）'
            steps.append(f'进入{label(kind, i, cid)}{where_txt}')
        parent_id = cid
    for n, s in enumerate(steps, 1):
        print(f'  {n}. {s}')
    lv = levels.get(lid)
    if lv:
        for _, _, key in lv.texts:
            print(f'  关卡里的提示：「{text(key)}」')
        try:
            m = sim.Model(lv)
            print('  地图（行列都从 1 开始数；# 墙，@ 恶魔，o/H/C 中性/热/冷块，t 透明，x 固定，L 关卡块，* 目标）：')
            for r, row in enumerate(m.render(m.initial()).split('\n'), 1):
                print(f'  {r:2} {row}')
        except NotImplementedError as e:
            print(f'  （地图里有尚未建模的机制：{e}）')
