"""Starting a search inside a level's real parent, as if just entered through its real block."""
import time
from . import mxw, sim, solver, world


def context_start(sv, lid, solved):
    w = sv.world
    parent = w.parent[lid]
    pm = w.model(parent, solved, sim.NEUTRAL)
    bi = pm.real_block[lid]
    px, py = pm.initial_pos[bi]
    occ = pm.occupancy(pm.initial())
    for d, (dx, dy) in enumerate(sim.DIRS):
        side = (px - dx, py - dy)  # the demon stood here and walked in direction d
        if pm.inside(side) and side not in occ:
            break
    else:
        raise ValueError('no free side next to the real block')
    t_out = pm.initial_temp[bi]
    m = w.model(lid, solved, t_out)
    s = m.initial()
    path = (world.Frame(parent, sim.NEUTRAL), world.Frame(lid, t_out, d, bi))
    return world.HState(solved, path, s, ())


