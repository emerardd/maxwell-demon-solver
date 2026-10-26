"""Solve a level through given intermediate layouts (sub-goals), stage by stage.

Usage: subgoal.py GAME_DIR LEVEL SECONDS BODY@X,Y[:C] ... [/ BODY@X,Y[:C] ...] ... [--out FILE]
BODY is a body index (see the block list printed first), X,Y its target cell, :C that it must
be cold there. A '/' starts a new stage; every stage must keep what the earlier ones reached.
Each stage is searched from where the previous one ended, guided by the push distance of every
listed body to its target (for a body not yet cold, through a cell where it gets chilled and
that it can be pushed out of again). Bodies needed by later stages must stay able to reach their
targets. A last phase continues to solving the level. The joined plan is replayed from the
level's start. Each stage gets SECONDS.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mdemon import mxw, sim, solver
from mdemon.staged import StagedSearch, finish, parse_stages

if __name__ == '__main__':
    args = sys.argv[1:]
    out_file = None
    if '--out' in args:
        i = args.index('--out')
        out_file = args[i + 1]
        del args[i:i + 2]
    game, lid, budget, specs = args[0], args[1], float(args[2]), args[3:]
    levels = mxw.load_world(game)[0]
    stages = parse_stages(specs)
    staged = StagedSearch(levels, lid, budget)
    m = staged.m
    targets = {k: v for st in stages for k, v in st.items()}
    print('blocks:')
    for bi, b in enumerate(m.bodies):
        if not b.outside:
            mark = ' <- target ' + str(targets[bi]) if bi in targets else ''
            print(f'  {bi:2} at {m.initial_pos[bi]} {sim.TEMP_CHAR[m.initial_temp[bi]]}'
                  f' faces(LDRU) {"".join("SPI"[f] for f in b.faces[0])}{mark}')
    plan = staged.run(stages)
    if plan is None or not finish(staged, plan, out_file):
        sys.exit(1)
