"""Find w1 levels where counting heat per cell vs per body can make a difference:
those with a hot or cold rigid body of more than one cell."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mxw, sim, run_world

levels, structure, _ = mxw.load_world(sys.argv[1])
for kind, lid in run_world.world_levels(structure, levels, 'w1'):
    m = sim.Model(levels[lid])
    multi = [(len(b.cells), sim.TEMP_CHAR[t]) for b, t in zip(m.bodies, m.initial_temp)
             if not b.outside and not b.transparent and len(b.cells) > 1]
    hotcold = [x for x in multi if x[1] != 'n']
    if hotcold:
        print(f'{kind:6} {lid}  multi-cell bodies (cells, temp): {multi}')
