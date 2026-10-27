"""Worlds and their level lists, from structure.json."""
from . import mxw

WORLDS = {'w1': '9a498c50', 'w2': '6c1848b0', 'w3': '214a0e55', 'w4': 'f1164388'}
KINDS = (('normalSublevels', 'normal'), ('extraSublevels', 'extra'), ('hintSublevels', 'hint'))


def find(node, lid):
    """The structure.json node of level lid, below node."""
    if node['id'] == lid:
        return node
    for k in ('normalSublevels', 'extraSublevels', 'metaSublevels', 'hintSublevels'):
        for ch in node.get(k, []):
            if r := find(ch, lid):
                return r


def world_levels(structure, levels, world, with_unreachable=False):
    """[(kind, level id)] below the world node (a key of WORLDS or a level id), depth first.
    Normal, extra and hint levels are included; meta levels and levels whose goals all lie
    outside the grid (world hint hubs) are not.

    A level listed under a hint level is normally a level block placed on that hint level's
    map. The one exception in the game data (a7674929) has no block anywhere, so it cannot be
    entered; such levels are left out, or returned with kind 'unreachable' if asked."""
    out = []

    def placed_in(parent_id, lid):
        parent = levels.get(parent_id)
        return parent is not None and any(isinstance(o, mxw.LevelBlock) and o.id == lid
                                          for row in parent.grid for o in row)

    def walk(node, kind, parent_kind=None, parent_id=None):
        if kind == 'hint' and parent_kind == 'hint' and not placed_in(parent_id, node['id']):
            if with_unreachable:
                out.append(('unreachable', node['id']))
            return
        lv = levels.get(node['id'])
        if lv and any(0 <= x < lv.w and 0 <= y < lv.h for x, y in lv.goals):
            out.append((kind, node['id']))
        for k, tag in KINDS:
            for ch in node.get(k, []):
                walk(ch, tag, kind, node['id'])
    root = find(structure['root'], WORLDS.get(world, world))
    for k, tag in KINDS:
        for ch in root.get(k, []):
            walk(ch, tag)
    return out


def labels(structure):
    """{level id: name in the game} for the worlds in WORLDS: 'w4-3', 'w4-C', 'w4-3 提示'
    (its hint level, H), 'w4 教程 2' (second level on the world's hint map)."""
    out = {}
    for world in WORLDS:
        node = find(structure['root'], WORLDS[world])
        out.update(numbered(structure, world))
        for k in ('normalSublevels', 'extraSublevels'):
            for ch in node.get(k, []):
                for h in ch.get('hintSublevels', []):
                    out.setdefault(h['id'], out[ch['id']] + ' 提示')
        for hub in node.get('hintSublevels', []):
            for i, ch in enumerate(hub.get('hintSublevels', []), 1):
                out.setdefault(ch['id'], f'{world} 教程 {i}')

    def nested(n):  # levels inside named levels: 'w3-5 / 2', 'w3-5 / B', 'w3-5 / 提示'
        for k, tag in (('normalSublevels', None), ('extraSublevels', 'letter'), ('hintSublevels', '提示')):
            kids = n.get(k, [])
            for i, ch in enumerate(kids, 1):
                if ch['id'] not in out and n['id'] in out:
                    sub = str(i) if tag is None else chr(64 + i) if tag == 'letter' else                         tag if len(kids) == 1 else f'{tag} {i}'
                    out[ch['id']] = f'{out[n["id"]]} / {sub}'
                nested(ch)
    for world in WORLDS:
        nested(find(structure['root'], WORLDS[world]))
    return out


def numbered(structure, world):
    """{level id: label} for a world's numbered and lettered levels, e.g. 'w1-15', 'w1-C'."""
    node = find(structure['root'], WORLDS.get(world, world))
    labels = {}
    for i, ch in enumerate(node.get('normalSublevels', []), 1):
        labels[ch['id']] = f'{world}-{i}'
    for i, ch in enumerate(node.get('extraSublevels', []), 1):
        labels[ch['id']] = f'{world}-{chr(64 + i)}'
    return labels
