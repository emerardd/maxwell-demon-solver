"""The solution database (solutions/db.json, see mdemon/store.py).

Usage:
  solutions.py list [WORLD]           best plan per level, and whether it was checked in the game
  solutions.py verify LEVEL [PLAN]    mark LEVEL's best plan (or PLAN) as passed in the game
  solutions.py tas LEVEL [FILE]       write a script for WYXkk/Maxwell-s-TAS-demon (default
                                      solutions/tas/<name>_<id>.txt)
  solutions.py import LEVEL FILE      add the plan of a walkthrough written by show_solution.py
LEVEL is an internal id or a name as in the list (w4-16, "w4-3 提示", ...). The game directory
comes from MXW_GAME_DIR, else the default Steam location.
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mdemon import catalog, mxw, sim, solver, store, world

GAME = os.environ.get('MXW_GAME_DIR',
                      r"D:\Program Files (x86)\Steam\steamapps\common\Maxwell's puzzling demon")
KEY = {'L': 'a', 'D': 's', 'R': 'd', 'U': 'w'}
ARROW = {'←': 'L', '↓': 'D', '→': 'R', '↑': 'U'}


def game():
    levels, structure, _ = mxw.load_world(GAME)
    return levels, structure, catalog.labels(structure)


def resolve(level, levels, labels):
    if level in levels:
        return level
    for lid, name in labels.items():
        if name == level:
            return lid
    sys.exit(f'unknown level {level!r}')


def order(labels):
    """Sort key: world, then numbered before lettered, then hint levels, by number."""
    def key(item):
        name, lid = item
        m = re.match(r'(w\d+)(?:-(\d+|[A-Z]))?(.*)', name or '')
        if not m:
            return ('~', 0, 0, name or lid)
        w, n, rest = m.groups()
        num = int(n) if n and n.isdigit() else (100 + ord(n) if n else 0)
        return (w, num, rest)
    return key


def cmd_list(args):
    levels, structure, labels = game()
    db = store.load()
    world_filter = args[0] if args else None
    rows = []
    for lid, entry in db.items():
        if not entry['plans']:
            continue
        name = labels.get(lid, '')
        if world_filter and not name.startswith(world_filter):
            continue
        plan, info = store.best(entry)
        if plan in entry['verified']:
            status = f'✓ 已通过（{entry["verified"][plan]}）'
        elif entry['verified']:
            v = min(store.moves(p) for p in entry['verified'])
            status = f'旧解已通过（{v} 步），最优解未验证'
        else:
            status = '未验证'
        rows.append(((name, lid), f'{lid}  {info["moves"]:4} 步  {len(entry["plans"]):2} 个解  {name or "-"}  {status}'))
    rows.sort(key=lambda r: order(labels)(r[0]))
    for _, line in rows:
        print(line)
    done = sum('✓' in line for _, line in rows)
    print(f'共 {len(rows)} 关有解，{done} 关的最优解已在游戏里通过')


def cmd_verify(args):
    levels, structure, labels = game()
    lid = resolve(args[0], levels, labels)
    plan = store.verify(lid, args[1] if len(args) > 1 else None)
    print(f'{labels.get(lid, lid)} {lid}: {store.moves(plan)} 步的解法标为游戏内已通过')


def tas_lines(levels, lid, plan_text, ctx):
    """The plan as TAS text, replayed through the rules to know where pistons move."""
    sv = solver.Solver(levels)
    w = sv.world
    kw = store.solve_kwargs(ctx)
    h = w.start(kw.get('scope') or lid, kw.get('solved', frozenset()), kw.get('t_out', sim.NEUTRAL))
    out = []
    for step in store.unflatten(plan_text):
        if isinstance(step, str):
            for letter in step:
                m = w.current(h)
                h = w.step(h, sim.DIR_NAMES.index(letter))
                if h is None:
                    raise ValueError(f'plan does not replay at {letter}')
                out.append(KEY[letter] + 'p' * m.last_extra)
                if not h.path or w.finished(h, lid):
                    out.append('-')
                    return out
        elif step[0] == 'enter':
            h = w.enter(h, sim.DIR_NAMES.index(step[1]))
            out.append(f'e  # 进入{"左下右上"[sim.DIR_NAMES.index(step[1])]}边的关卡块\n')
        else:
            if out:
                out[-1] = out[-1][0].upper() + out[-1][1:]  # the move before quitting waits longer
            h = w.quit(h)
            out.append('q\n')
        if h is None:
            raise ValueError('plan does not replay')
    return out


def cmd_tas(args):
    levels, structure, labels = game()
    lid = resolve(args[0], levels, labels)
    entry = store.load().get(lid)
    if not entry:
        sys.exit(f'no plan stored for {lid}')
    plan, info = store.best(entry)
    name = labels.get(lid, lid)
    path = args[1] if len(args) > 1 else os.path.join(
        store.ROOT, 'solutions', 'tas', f'{name.replace(" ", "_")}_{lid}.txt')
    keys = tas_lines(levels, lid, plan, info['ctx'])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f'# {name} ({lid}), {info["moves"]} moves, for WYXkk/Maxwell-s-TAS-demon\n')
        f.write('# start inside the level, at its start (enter it by hand first)\n')
        if info['ctx']:
            f.write(f'# context: {info["ctx"]}\n')
        line = ''
        for k in keys:
            line += k
            if line.endswith('\n') or len(line) >= 40:
                f.write(line.rstrip('\n') + '\n')
                line = ''
        if line:
            f.write(line + '\n')
    print(f'{name} {lid}: {info["moves"]} 步 -> {path}')


def cmd_import(args):
    levels, structure, labels = game()
    lid = resolve(args[0], levels, labels)
    text = open(args[1], encoding='utf-8').read()
    plan = ''.join(ARROW[c] for line in re.findall(r'第 \d+-\d+ 步：(.*)', text)
                   for c in line.split())
    sv = solver.Solver(levels)
    if not solver.replay(sv, lid, store.unflatten(plan))[0]:
        sys.exit(f'{args[1]}: the plan does not solve {lid}')
    store.record(lid, plan, source=f'import {os.path.basename(args[1])}')
    print(f'{labels.get(lid, lid)} {lid}: {store.moves(plan)} 步，已导入')


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in ('list', 'verify', 'tas', 'import'):
        sys.exit(__doc__)
    globals()['cmd_' + sys.argv[1]](sys.argv[2:])
