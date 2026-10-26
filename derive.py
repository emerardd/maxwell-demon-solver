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
5. The stages go to subgoal.StagedSearch; layouts and orders are tried until one works.
Only single-cell carrier blocks are considered, and one hazard group (the first found).
"""
import itertools, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mxw, prune, sim
from subgoal import StagedSearch, chill_spots, finish, push_distances


def walkable(m, static, frm, blocked):
    """Cells the demon can walk to from frm without pushing anything in blocked."""
    seen, stack = {frm}, [frm]
    while stack:
        c = stack.pop()
        for dx, dy in sim.DIRS:
            n = (c[0] + dx, c[1] + dy)
            if n not in seen and m.inside(n) and n not in static and n not in blocked:
                seen.add(n)
                stack.append(n)
    return seen


class Derivation:
    def __init__(self, levels, lid, budget, log=print):
        self.staged = StagedSearch(levels, lid, budget, log)
        self.m, self.t, self.log = self.staged.m, self.staged.tables, log
        self.s = self.m.initial()
        self.static = self.t.static

    # -- 1, 2: final pushes and hazards ----------------------------------------------------------
    def final_pushes(self):
        """(candidate body, cells its origin passes, cells the demon stands on)."""
        best = None
        for d, table, origin, shape, members in self.staged.sv.pruner._candidates(self.m, self.s, self.t):
            if len(members) == 1 and len(shape) == 1 and (best is None or d < best[0]):
                best = (d, table, origin, members[0])
        if best is None:
            return None
        _, table, o, body = best
        route, demon = [o], []
        while table.get(o, 0) > 0:
            nxt = next(n for n in ((o[0] + dx, o[1] + dy) for dx, dy in sim.DIRS)
                       if table.get(n) == table[o] - 1)
            demon += [(2 * o[0] - nxt[0], 2 * o[1] - nxt[1]), o]  # behind before, in place after
            o = nxt
            route.append(o)
        return body, route, demon

    def hazards(self, cells):
        """Hot groups touching the demon on any of cells: {rep: (members, hot cells)}."""
        m, s = self.m, self.s
        occ = m.occupancy(s)
        groups = m.groups(s.glue)
        found = {}
        for c in cells:
            for i, (dx, dy) in enumerate(sim.DIRS):
                hit = occ.get((c[0] + dx, c[1] + dy))
                if hit and s.temp[hit[0]] == sim.HOT and not m.bodies[hit[0]].outside \
                        and m.bodies[hit[0]].faces[hit[1]][sim.OPP[i]] != sim.INSULATED:
                    rep = s.glue[hit[0]]
                    members = groups[rep][0]
                    found[rep] = (members, {(s.pos[j][0] + cx, s.pos[j][1] + cy)
                                            for j in members for cx, cy in m.bodies[j].cells})
        return found

    # -- 3: cooling layouts ------------------------------------------------------------------------
    def carriers(self, exclude):
        m, s = self.m, self.s
        groups = m.groups(s.glue)
        out = []
        for bi, b in enumerate(m.bodies):
            if bi in exclude or b.fixed or b.outside or b.level_id or len(b.cells) != 1 \
                    or not b.weight or s.temp[bi] == sim.HOT or len(groups[s.glue[bi]][0]) != 1:
                continue
            if any(f != sim.INSULATED for f in b.faces[0]):
                out.append(bi)
        return out

    def layouts(self, hazard_cells, need, avoid, carriers, limit=200):
        """Yield (bridge cell, {cell: body}) cooling layouts, in order of total push distance."""
        m, s = self.m, self.s
        occ = m.occupancy(s)

        def free(c):
            return m.inside(c) and c not in self.static and c not in hazard_cells and c not in avoid

        def touches_hazard(cell, bi):
            for i, (dx, dy) in enumerate(sim.DIRS):
                n = (cell[0] + dx, cell[1] + dy)
                hit = occ.get(n)
                if n in hazard_cells and m.bodies[bi].faces[0][i] != sim.INSULATED \
                        and m.bodies[hit[0]].faces[hit[1]][sim.OPP[i]] != sim.INSULATED:
                    return True
            return False

        reach = {}  # (cell, body) -> pushes from the body's start, if it can get there at all

        def cost(cell, bi):
            key = (cell, bi)
            if key not in reach:
                reach[key] = push_distances(m, self.static, cell).get(s.pos[bi])
            return reach[key]

        bridges = []
        for hc in hazard_cells:
            hit = occ[hc]
            for i, (dx, dy) in enumerate(sim.DIRS):
                d = (hc[0] + dx, hc[1] + dy)
                if free(d) and m.bodies[hit[0]].faces[hit[1]][i] != sim.INSULATED:
                    bridges.append(d)
        found = []
        seen = set()

        def grow(bridge, placed, used, weight):
            if len(found) >= limit:
                return
            key = (bridge, frozenset(placed.items()))
            if key in seen:
                return
            seen.add(key)
            if weight >= need:
                found.append((sum(cost(c, b) for c, b in placed.items()), bridge, dict(placed)))
                return
            # ports: cells next to the bridge (the demon conducts on every side) or next to a
            # placed block through one of its conductive faces
            ports = [(bridge, i) for i in range(4)]
            ports += [(c, i) for c, b in placed.items() for i in range(4)
                      if m.bodies[b].faces[0][i] != sim.INSULATED]
            for src, i in ports:
                cell = (src[0] + sim.DIRS[i][0], src[1] + sim.DIRS[i][1])
                if cell == bridge or cell in placed or not free(cell):
                    continue
                for bi in carriers:
                    if bi in used or m.bodies[bi].faces[0][sim.OPP[i]] == sim.INSULATED:
                        continue
                    if touches_hazard(cell, bi) or cost(cell, bi) is None:
                        continue
                    placed[cell] = bi
                    grow(bridge, placed, used | {bi}, weight + m.bodies[bi].weight)
                    del placed[cell]

        for bridge in bridges:
            grow(bridge, {}, frozenset(), 0)
        found.sort(key=lambda f: f[0])
        for _, bridge, placed in found:
            yield bridge, placed

    # -- 4: stage order ----------------------------------------------------------------------------
    def orders(self, placed):
        """Yield placement orders [(body, cell)] in which every block can be chilled and placed."""
        m = self.m
        items = [(b, c) for c, b in placed.items()]
        for order in itertools.permutations(items):
            pos, temp = list(self.s.pos), list(self.s.temp)
            blocked, ok = set(), True
            for b, cell in order:
                s = self.s._replace(pos=tuple(pos), temp=tuple(temp))
                to_cell = push_distances(m, self.static, cell, blocked)
                if temp[b] == sim.COLD:
                    ok = s.pos[b] in to_cell
                else:
                    ok = any(s.pos[b] in push_distances(m, self.static, a, blocked) and a in to_cell
                             for a in chill_spots(m, s, self.static, b, blocked))
                if not ok:
                    break
                pos[b], temp[b] = cell, sim.COLD
                blocked.add(cell)
            if ok:
                yield list(order)

    # -- 5: everything together --------------------------------------------------------------------
    def solve(self, max_layouts=5, max_orders=3):
        log = self.log
        fp = self.final_pushes()
        if fp is None:
            log('no single-cell candidate block can reach the goal')
            return None
        body, route, demon = fp
        log(f'candidate block {body} at {route[0]}, route {route}, demon on {demon}')
        hz = self.hazards(demon)
        if not hz:
            log('no hazard on the final pushes: an ordinary search should do')
            return None
        rep, (members, cells) = next(iter(hz.items()))
        need = sum(self.m.bodies[j].weight for j in members)
        log(f'hazard: hot group {members} on {sorted(cells)}, {need} units of heat to cancel')
        carriers = self.carriers({body} | set(members))
        log(f'carrier blocks: {carriers}')
        avoid = set(route) | set(demon)
        start = self.s.demon
        tried = 0
        for bridge, placed in self.layouts(cells, need, avoid, carriers):
            # the demon walks around the layout, the hazard and the candidate block
            walls = set(placed) | cells | {route[0]}
            reach = walkable(self.m, self.static, start, walls)
            if bridge not in reach or not all(c in reach or c == route[0] for c in demon):
                continue  # the layout would wall the demon off from the bridge or the final pushes
            tried += 1
            if tried > max_layouts:
                break
            log(f'layout {tried}: bridge {bridge}, blocks {placed}')
            for k, order in enumerate(self.orders(placed)):
                if k >= max_orders:
                    break
                log(f'  order {[b for b, _ in order]}')
                stages = [{b: (cell, True)} for b, cell in order]
                plan = self.staged.run(stages)
                if plan is not None:
                    return plan
        log('no layout and order led to a solution')
        return None


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
