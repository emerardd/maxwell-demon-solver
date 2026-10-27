"""The solution database (solutions/db.json, see mdemon/store.py).

Usage:
  solutions.py list [WORLD]           best plan per level, and whether it was checked in the game
  solutions.py verify LEVEL [PLAN]    mark LEVEL's best plan (or PLAN) as passed in the game
  solutions.py play LEVEL [--dry]     press the keys of LEVEL's best plan in the running game
                                      (mdemon/play.py); --dry only prints them
  solutions.py tour WORLD [--dry] [--budget S]
                                      play the numbered and lettered levels of WORLD one after
                                      the other from the start of its map, walking between them;
                                      S: seconds per search for the way to a block (default 20)
  solutions.py tas LEVEL [FILE]       write a script for WYXkk/Maxwell-s-TAS-demon (default
                                      solutions/tas/<name>_<id>.txt)
  solutions.py import LEVEL FILE      add the plan of a walkthrough written by show_solution.py
LEVEL is an internal id or a name as in the list (w4-16, "w4-3 提示", ...). The game directory
comes from MXW_GAME_DIR, else the default Steam location.
"""
import json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mdemon import catalog, mxw, play, solver, store

GAME = os.environ.get('MXW_GAME_DIR',
                      r"D:\Program Files (x86)\Steam\steamapps\common\Maxwell's puzzling demon")
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
    keys = play.tas_text(play.actions(levels, lid, plan, info['ctx']))
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


def cmd_play(args):
    levels, structure, labels = game()
    lid = resolve(args[0], levels, labels)
    entry = store.load().get(lid)
    if not entry:
        sys.exit(f'no plan stored for {lid}')
    plan, info = store.best(entry)
    name = labels.get(lid, lid)
    acts = play.actions(levels, lid, plan, info['ctx'])
    sched = play.schedule(acts)
    total = sum(w for _, w in sched) / 1000
    pistons = sum(e for _, _, e in acts)
    print(f'{name} {lid}: {len(sched)} 键（活塞额外动作 {pistons} 次），约 {total:.0f} 秒')
    if info['ctx']:
        print(f'注意：这条解法要从特定上下文开始：{info["ctx"]}')
    if '--dry' in args:
        print(' '.join(f'{k}{w}' for k, w in sched))
        return
    player = play.Player()
    print('请切到游戏窗口，进入这一关并停在起点。检测到游戏窗口在前台后 3 秒开始；'
          '中途切走会暂停，按住 F8 停止。')
    if not player.wait_for_game(print):
        sys.exit('60 秒内没有切到游戏窗口，已取消')
    for i in (3, 2, 1):
        print(f'{i}...', flush=True)
        time.sleep(1)
    sent = player.play(sched)
    if sent < len(sched):
        return
    answer = input('游戏里过关了吗？(y/N) ').strip().lower()
    if answer == 'y':
        store.verify(lid, plan)
        print(f'{name} {lid}: {info["moves"]} 步的解法标为游戏内已通过')


def subtree(node):
    ids = {node['id']}
    for k in ('normalSublevels', 'extraSublevels', 'metaSublevels', 'hintSublevels'):
        for ch in node.get(k, []):
            ids |= subtree(ch)
    return ids


def cmd_tour(args):
    levels, structure, labels = game()
    world = args[0]
    node = catalog.find(structure['root'], catalog.WORLDS[world])
    db = store.load()
    todo, plans = [], {}
    for k in ('normalSublevels', 'extraSublevels'):
        for ch in node.get(k, []):
            entry = db.get(ch['id'])
            if entry and entry['plans']:
                plan, info = store.best(entry)
                if not info['ctx']:  # plans needing another context cannot be toured
                    todo.append(ch['id'])
                    plans[ch['id']] = plan
    # The route is planned once per set of plans and kept in solutions/tours/<world>.json.
    # The save is taken to have every level of the world solved, so the map looks as in the game.
    cache = os.path.join(store.ROOT, 'solutions', 'tours', f'{world}.json')
    segments = skipped = None
    if os.path.exists(cache):
        with open(cache, encoding='utf-8') as f:
            kept = json.load(f)
        if kept['plans'] == plans:
            segments = [(lid, [tuple(a) for a in acts]) for lid, acts in kept['segments']]
            skipped = [tuple(s) for s in kept['skipped']]
            print(f'用缓存的路线 {cache}')
    if segments is None:
        segments, skipped = play.tour(levels, node['id'], todo, plans, frozenset(subtree(node)),
                                      budget=float(args[args.index('--budget') + 1]) if '--budget' in args else 20,
                                      log=lambda line: print('  规划 ' + line, flush=True))
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, 'w', encoding='utf-8') as f:
            json.dump({'plans': plans, 'segments': segments, 'skipped': skipped}, f,
                      ensure_ascii=False, indent=1)
    for lid, why in skipped:
        print(f'跳过 {labels.get(lid, lid)} {lid}：{why}')
    sched = [play.schedule(acts) for _, acts in segments]
    total = sum(w for s in sched for _, w in s) / 1000
    print(f'{world}：连播 {len(segments)} 关，共 {sum(len(s) for s in sched)} 键，约 {total / 60:.1f} 分钟')
    for n, (lid, acts) in enumerate(segments, 1):
        print(f'  {n:2}. {labels.get(lid, lid):8} {lid}  {len(acts)} 键')
    if '--dry' in args or not segments:
        return
    player = play.Player()
    print(f'请在游戏里进入 {world}，停在世界地图的起点（游戏存档里 {world} 要已经全部解开），'
          '然后切到游戏窗口。检测到游戏在前台后 3 秒开始；中途切走会暂停，按住 F8 停止。')
    if not player.wait_for_game(print):
        sys.exit('60 秒内没有切到游戏窗口，已取消')
    for i in (3, 2, 1):
        print(f'{i}...', flush=True)
        time.sleep(1)
    finished = 0
    for n, ((lid, acts), s) in enumerate(zip(segments, sched), 1):
        print(f'[{n}/{len(segments)}] {labels.get(lid, lid)} {lid}', flush=True)
        if player.play(s, log=lambda line: None) < len(s):
            print(f'在第 {n} 关 {labels.get(lid, lid)} 中途停止')
            break
        finished = n
    answer = input(f'已播完 {finished} 关。从第几关开始出错？（输入序号；回车 = 这 {finished} 关全部通过） ').strip()
    good = finished if not answer else max(0, min(finished, int(answer) - 1))
    for lid, _ in segments[:good]:
        store.verify(lid, plans[lid])
    print(f'{good} 关标为游戏内已通过')


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
    if len(sys.argv) < 2 or sys.argv[1] not in ('list', 'verify', 'play', 'tour', 'tas', 'import'):
        sys.exit(__doc__)
    globals()['cmd_' + sys.argv[1]](sys.argv[2:])
