"""Solve every level of a world with the simulator and replay each plan.

Usage: run_world.py GAME_DIR WORLD [cell|body] [seconds per level, default 60] [level ids ...]
WORLD is a key of WORLDS (w1, w2, ...) or a level id. Normal, extra and hint levels are
included; meta levels and levels whose goals all lie outside the grid (world hint hubs) are not.
Each level first gets optimal A* for half the budget; on timeout, weighted A* (h x3) gets the
full budget. Results: OK = shortest plan, OK~ = plan from weighted A* (maybe not shortest),
NOBLOCKS = the level holds nothing that could stand on its goal (not a puzzle on its own).
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mxw, prune, sim, solver

WORLDS = {'w1': '9a498c50', 'w2': '6c1848b0'}
KINDS = (('normalSublevels', 'normal'), ('extraSublevels', 'extra'), ('hintSublevels', 'hint'))


def find(node, lid):
    if node['id'] == lid:
        return node
    for k in ('normalSublevels', 'extraSublevels', 'metaSublevels', 'hintSublevels'):
        for ch in node.get(k, []):
            if r := find(ch, lid):
                return r


def world_levels(structure, levels, world, with_unreachable=False):
    """[(kind, level id)] below the world node, depth first.

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


def progress(lid, states, queued, depth):
    print(f'      ... {lid}: {states:,} states, {queued:,} queued, depth {depth}', flush=True)


if __name__ == '__main__':
    levels, structure, _ = mxw.load_world(sys.argv[1])
    world = sys.argv[2]
    weight = sys.argv[3] if len(sys.argv) > 3 else 'cell'
    budget = float(sys.argv[4]) if len(sys.argv) > 4 else 60
    only = set(sys.argv[5:])
    optimal = solver.Solver(levels, weight=weight, time_budget=budget / 2, progress=progress)
    fast = solver.Solver(levels, weight=weight, time_budget=budget, progress=progress, h_weight=3)
    todo = [x for x in world_levels(structure, levels, world) if not only or x[1] in only]
    results = {}
    for n, (kind, lid) in enumerate(todo, 1):
        print(f'[{n}/{len(todo)}] {kind} {lid} ...', flush=True)
        t = time.time()
        try:
            no_blocks = not any(prune.is_candidate(b) for b in sim.Model(levels[lid]).bodies)
        except NotImplementedError:
            no_blocks = False
        if no_blocks:  # nothing could ever stand on the goal, e.g. an empty level used as a door
            results[lid] = (kind, 'NOBLOCKS')
            print(f'{kind:6} {lid} NOBLOCKS     0.0s  no block that could stand on the goal', flush=True)
            continue
        for sv, ok_tag in ((optimal, 'OK'), (fast, 'OK~')):
            try:
                r = sv.solve(lid)
                status = ok_tag if r and solver.replay(sv, lid, r[0])[0] else ('BADPLAN' if r else 'UNSOLVABLE')
                msg = f'{len(solver.flatten(r[0]))} chars  {solver.flatten(r[0])[:90]}' if r else ''
                break
            except TimeoutError as e:
                status, msg = 'TIMEOUT', str(e)
                if sv is optimal:
                    print(f'      optimal A* timed out, retrying with weighted A*', flush=True)
            except (RuntimeError, NotImplementedError) as e:
                status, msg = 'ERROR', str(e)
                break
        results[lid] = (kind, status)
        print(f'{kind:6} {lid} {status:10} {time.time() - t:5.1f}s  {msg}', flush=True)
    ok = sum(s.startswith('OK') for _, s in results.values())
    print(f'\n{world} weight={weight}, budget={budget:g}s: {ok}/{len(todo)} solved and replayed')
    for lid, (kind, s) in results.items():
        if s != 'OK':  # OK~ is listed too: worth a second look
            print(f'  {s:10} {kind:6} {lid}')
