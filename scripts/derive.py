"""Derive the final layout and the stage order of a "shuffle" level automatically, then solve it.

Usage: derive.py GAME_DIR LEVEL [seconds per stage, default 30] [--out FILE]

Works backwards from the goal, for levels where the last pushes are blocked by heat:
1. Final pushes: the candidate block nearest to the goal (by push distance) and the cells the
   demon must stand on to push it there (behind it before each push, in its place after).
2. Hazards: hot groups that would touch the demon on one of those cells through a conductive
   face. The demon would burn, so the hazard must be cancelled first.
3. Cooling layouts (a small constraint search): a bridge cell next to the hazard, where the
   standing demon connects the hazard with a group of cold blocks, and blocks attached one by
   one through pairs of conductive faces until the group holds at least as much cold as the
   hazard holds heat. A block may not touch the hazard itself (it would heat up before the
   group is complete), may not stand on the final route or on the demon's cells, and must be
   able to get to its cell by pushes. The demon must still be able to walk to the bridge cell
   and to the final push cells with the layout in place.
4. Stage order: blocks are placed one per stage; an order is kept if every block, with the
   blocks placed before it standing as walls, can be pushed to a cell where it gets chilled
   (by a cold block, the ones already placed included, possibly with the demon relaying) and
   from there to its cell.
5. The stages go to mdemon.staged.StagedSearch; layouts and orders are tried until one works.
Only single-cell carrier blocks are considered, and one hazard group (the first found).
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mdemon import mxw, sim, solver
from mdemon.derive import Derivation
from mdemon.staged import finish

if __name__ == '__main__':
    args = sys.argv[1:]
    out_file = None
    if '--out' in args:
        i = args.index('--out')
        out_file = args[i + 1]
        del args[i:i + 2]
    levels = mxw.load_world(args[0])[0]
    lid = args[1]
    budget = float(args[2]) if len(args) > 2 else 30
    t = time.time()
    d = Derivation(levels, lid, budget)
    plan = d.solve()
    print(f'total {time.time() - t:.1f}s')
    if plan is None or not finish(d.staged, plan, out_file):
        sys.exit(1)
