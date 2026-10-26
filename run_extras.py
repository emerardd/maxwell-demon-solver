"""Solve the lettered (extra) levels of worlds with every tool we have, and summarise.

Usage: run_extras.py GAME_DIR [seconds for solve_any, default 60] [worlds, default w1 w2 w3]
Per level: solve_any (guided search, then shortest-plan A*); if that gives nothing, derive.py
(cooling layout + staged sub-goals, 30 s per stage). Plans are replayed before they count.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import derive, mxw, run_world, solver

game = sys.argv[1]
budget = float(sys.argv[2]) if len(sys.argv) > 2 else 60
worlds = sys.argv[3:] or ['w1', 'w2', 'w3']
levels, structure, _ = mxw.load_world(game)

todo = []
for world in worlds:
    node = run_world.find(structure['root'], run_world.WORLDS[world])
    for i, ch in enumerate(node.get('extraSublevels', []), 1):
        todo.append((world, chr(64 + i), ch['id']))

results = []
for n, (world, letter, lid) in enumerate(todo, 1):
    print(f'[{n}/{len(todo)}] {world}-{letter} ({lid}) ...', flush=True)
    t = time.time()
    status, msg = None, ''
    try:
        r = solver.solve_any(levels, lid, budget)
        if r is None:
            status = 'UNSOLVABLE'
        else:
            sv, plan, _ = r
            ok = solver.replay(sv, lid, plan)[0]
            status = 'OK' if ok else 'BADPLAN'
            msg = f'{len(solver.flatten(plan))} chars'
    except TimeoutError:
        status = 'TIMEOUT'
    except NotImplementedError as e:
        status, msg = 'ERROR', str(e)
    if status in ('TIMEOUT', 'UNSOLVABLE'):
        print(f'      solve_any: {status}, trying derive.py', flush=True)
        try:
            d = derive.Derivation(levels, lid, 30, log=lambda line: print('      ' + str(line).replace('\n', '\n      '), flush=True))
            plan = d.solve()
            if plan is not None and solver.replay(d.staged.sv, lid, plan)[0]:
                status, msg = 'OK(derive)', f'{len(solver.flatten(plan))} chars'
        except NotImplementedError as e:
            msg = str(e)
    results.append((world, letter, lid, status, time.time() - t, msg))
    print(f'{world}-{letter} {lid} {status:11} {time.time() - t:6.1f}s  {msg}', flush=True)

print('\nsummary:')
for world in worlds:
    rows = [r for r in results if r[0] == world]
    ok = sum(r[3].startswith('OK') for r in rows)
    print(f'  {world}: {ok}/{len(rows)} solved')
    for _, letter, lid, status, secs, msg in rows:
        print(f'    {letter} {lid} {status:11} {secs:6.1f}s  {msg}')
