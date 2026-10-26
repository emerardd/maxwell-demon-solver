"""Worlds and their level lists, from structure.json."""
from . import mxw

WORLDS = {'w1': '9a498c50', 'w2': '6c1848b0', 'w3': '214a0e55'}
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


def numbered(structure, world):
    """{level id: label} for a world's numbered and lettered levels, e.g. 'w1-15', 'w1-C'."""
    node = find(structure['root'], WORLDS.get(world, world))
    labels = {}
    for i, ch in enumerate(node.get('normalSublevels', []), 1):
        labels[ch['id']] = f'{world}-{i}'
    for i, ch in enumerate(node.get('extraSublevels', []), 1):
        labels[ch['id']] = f'{world}-{chr(64 + i)}'
    return labels
