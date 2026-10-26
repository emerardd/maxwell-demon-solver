"""Rule tests for the mdemon package, grouped by tutorial text, plus game data tests.
Run from the repository root: python -m unittest discover -s tests

Levels are drawn in a small ASCII language:
    #  fixed boundary wall (insulated toward the room)   w  boundary wall with a conductive face
    .  floor        *  goal        @  demon start
    o  neutral block   h  hot block   c  cold block      (conductive on all sides)
    O  insulated neutral block   x  fixed neutral block
    t  transparent block
    A..Z  level block, linked to a level id through `links`: 'X' is the real block of level X,
          '~X' a shortcut to it
Set MXW_GAME_DIR to also run the data tests against the installed game.
"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mdemon import mxw, prune, sim, solver, world
from mdemon.sim import HOT, COLD, NEUTRAL

L, D, R, U = range(4)
ATTR = {'o': 2, 'h': 6, 'c': 10, 'O': 2, 'x': 3, 't': 0, '#': 3, 'w': 3}
UNSOLVED, SOLVED = mxw.Block(3, 0xaa), mxw.Block(2, 0x55)  # fixed + insulated, then movable


def build(rows, faces=None, links=None, lid='test'):
    """faces: {(x, y): (left, down, right, up)} overrides for single blocks.
    links: {letter: level id ('~id' for a shortcut), or (level id, unsolved Block, solved Block)}."""
    h, w = len(rows), len(rows[0])
    grid, goals = [], []
    for y, row in enumerate(rows):
        line = []
        for x, ch in enumerate(row):
            if links and ch in links:
                spec = links[ch]
                target, unsolved, solved = (spec, UNSOLVED, SOLVED) if isinstance(spec, str) else spec
                flag = 0 if target.startswith('~') else 1
                line.append(mxw.LevelBlock(flag, target.lstrip('~'), unsolved, solved))
            elif ch in '.*':
                line.append(None)
                if ch == '*':
                    goals.append((x, y))
            elif ch == '@':
                line.append(mxw.Start())
            else:
                codes = []
                for dx, dy in sim.DIRS:
                    n = rows[y + dy][x + dx] if 0 <= y + dy < h and 0 <= x + dx < w else '#'
                    if ch in '#w':
                        codes.append(sim.MERGED if n in '#w' else (sim.PLAIN if ch == 'w' else sim.INSULATED))
                    else:
                        codes.append(sim.INSULATED if ch == 'O' else sim.PLAIN)
                if faces and (x, y) in faces:
                    codes = list(faces[(x, y)])
                line.append(mxw.Block(ATTR[ch], sum(c << (2 * i) for i, c in enumerate(codes))))
        grid.append(line)
    return mxw.Level(lid, w, h, grid, goals)


def run(rows, moves, t_out=NEUTRAL, faces=None):
    m = sim.Model(build(rows, faces), t_out=t_out)
    s = m.initial()
    for d in moves:
        s = m.step(s, d)
        if s is None:
            return m, None
    return m, s


def temp_at(m, s, cell):
    return s.temp[m.occupancy(s)[cell][0]]


class Walls(unittest.TestCase):
    def test_unpinned_wall_cells_belong_to_the_outside(self):
        # in the game files walls alternate pinned (attr 3) and unpinned (attr 2) cells
        level = build(['#####',
                       '#@.*#',
                       '#####'])
        for y, row in enumerate(level.grid):
            for x, o in enumerate(row):
                if isinstance(o, mxw.Block) and (x + y) % 2:
                    row[x] = mxw.Block(2, o.sides)
        m = sim.Model(level)
        walls = [b for b in m.bodies if b.outside]
        self.assertEqual(len(walls), 1)
        self.assertEqual(len(m.bodies), 1)


class Pushing(unittest.TestCase):
    def test_walk_and_push(self):
        m, s = run(['#######',
                    '#@.o..#',
                    '#######'], [R, R])
        self.assertEqual(s.demon, (3, 1))
        self.assertIn((4, 1), m.occupancy(s))

    def test_push_chain(self):
        m, s = run(['#######',
                    '#@oo..#',
                    '#######'], [R])
        occ = m.occupancy(s)
        self.assertIn((3, 1), occ)
        self.assertIn((4, 1), occ)

    def test_push_into_wall_fails(self):
        _, s = run(['####',
                    '#@o#',
                    '####'], [R])
        self.assertIsNone(s)

    def test_fixed_block_cannot_move(self):  # w1/fixed
        _, s = run(['#####',
                    '#@x.#',
                    '#####'], [R])
        self.assertIsNone(s)

    def test_multi_cell_body_moves_rigidly(self):
        rows = ['#######',
                '#..o..#',
                '#@.o..#',
                '#######']
        faces = {(3, 1): (1, 0, 1, 1), (3, 2): (1, 1, 1, 0)}  # merged vertically
        m, s = run(rows, [R, R], faces=faces)
        occ = m.occupancy(s)
        self.assertEqual(s.glue[occ[(4, 1)][0]], s.glue[occ[(4, 2)][0]])

    def test_blocked_multi_cell_body(self):
        rows = ['#######',
                '#..ox.#',
                '#@.o..#',
                '#######']
        faces = {(3, 1): (1, 0, 1, 1), (3, 2): (1, 1, 1, 0)}
        _, s = run(rows, [R, R], faces=faces)
        self.assertIsNone(s)


class Temperature(unittest.TestCase):
    def test_touching_hot_kills_demon(self):  # w1/temperature
        m, s = run(['######',
                    '#@.h.#',
                    '######'], [R])
        self.assertTrue(m.lost(s))
        self.assertIsNone(m.step(s, L))

    def test_touching_cold_is_safe(self):
        m, s = run(['######',
                    '#@.c.#',
                    '######'], [R])
        self.assertEqual(s.demon_temp, COLD)
        self.assertFalse(m.lost(s))
        self.assertIsNotNone(m.step(s, L))

    def test_demon_stores_no_heat(self):  # w1/demon
        m, s = run(['#######',
                    '#@.c..#',
                    '#######'], [R, L])
        self.assertEqual(s.demon_temp, NEUTRAL)


class HeatExchange(unittest.TestCase):  # w1/heat
    def test_hot_meets_neutral(self):
        m, s = run(['#######',
                    '#@o.h.#',
                    '#######'], [R])
        self.assertEqual(temp_at(m, s, (3, 1)), HOT)
        self.assertEqual(temp_at(m, s, (4, 1)), HOT)

    def test_equal_amounts_neutralise(self):
        m, s = run(['#######',
                    '#@h.c.#',
                    '#######'], [R])
        self.assertEqual(temp_at(m, s, (3, 1)), NEUTRAL)
        self.assertEqual(temp_at(m, s, (4, 1)), NEUTRAL)
        self.assertFalse(m.lost(s))

    def test_majority_wins_whole_component(self):
        m, s = run(['########',
                    '#@c.hh.#',
                    '########'], [R])
        for x in (3, 4, 5):
            self.assertEqual(temp_at(m, s, (x, 1)), HOT)

    def test_demon_conducts_but_does_not_count(self):  # w1/demon
        # demon steps between a hot and a cold block: 1 hot vs 1 cold, demon not counted
        m, s = run(['#######',
                    '#h.c..#',
                    '#.@...#',
                    '#######'], [U])
        self.assertEqual(s.demon, (2, 1))
        self.assertEqual(s.demon_temp, NEUTRAL)
        self.assertEqual(temp_at(m, s, (1, 1)), NEUTRAL)

    def test_demon_bridge_two_hot_one_cold(self):
        # 2 hot vs 1 cold joined through the demon: everything turns hot, demon included
        m, s = run(['#######',
                    '#hh.c.#',
                    '#..@..#',
                    '#######'], [U])
        self.assertEqual(temp_at(m, s, (4, 1)), HOT)
        self.assertTrue(m.lost(s))

    def test_multi_cell_body_counts_per_cell(self):
        # a 2-cell cold bar balances two hot blocks (confirmed by hint level cde27355)
        faces = {(4, 1): (1, 1, 0, 1), (5, 1): (0, 1, 1, 1)}
        m, s = run(['########',
                    '#hh.cc.#',
                    '#..@...#',
                    '########'], [U], faces=faces)
        self.assertEqual(temp_at(m, s, (4, 1)), NEUTRAL)
        self.assertEqual(temp_at(m, s, (1, 1)), NEUTRAL)
        self.assertFalse(m.lost(s))

    def test_transparent_does_not_count(self):  # w2 rule, needed so heat weights are right
        m, s = run(['#######',
                    '#@t.c.#',
                    '#######'], [R])
        self.assertEqual(temp_at(m, s, (4, 1)), COLD)


class Insulation(unittest.TestCase):
    def test_insulated_block_keeps_temperature(self):  # w1/insulated-1
        m, s = run(['#######',
                    '#@O.h.#',
                    '#######'], [R])
        self.assertEqual(temp_at(m, s, (3, 1)), NEUTRAL)
        self.assertEqual(temp_at(m, s, (4, 1)), HOT)

    def test_partial_insulation(self):  # w1/insulated-2
        # block insulated only on its right face: heat passes on the left, not on the right
        faces = {(3, 1): (1, 1, 2, 1)}
        m, s = run(['########',
                    '#@.o.h.#',
                    '########'], [R, R], faces=faces)
        self.assertEqual(temp_at(m, s, (4, 1)), NEUTRAL)
        m, s = run(['########',
                    '#h.o.@.#',
                    '########'], [L, L], faces=faces)
        self.assertEqual(temp_at(m, s, (2, 1)), HOT)
        self.assertFalse(m.lost(s))  # the demon only touches the insulated right face

    def test_insulated_hot_block_is_safe_to_touch(self):
        faces = {(3, 1): (2, 2, 2, 2)}
        m, s = run(['######',
                    '#@.h.#',
                    '######'], [R], faces=faces)
        self.assertFalse(m.lost(s))


class OuterBoundary(unittest.TestCase):  # w1/outer
    def test_block_next_to_conductive_boundary_takes_outside_temp(self):
        m, s = run(['#####w#',
                    '#@.o..#',
                    '#######'], [R, R, R], t_out=COLD)
        self.assertEqual(temp_at(m, s, (5, 1)), COLD)

    def test_outside_is_infinite(self):
        # two hot blocks under a window to a cold outside: both turn cold at once,
        # so the demon stepping next to them in the same turn is safe
        m, s = run(['###ww##',
                    '#@.hh.#',
                    '#######'], [R], t_out=COLD)
        self.assertEqual(temp_at(m, s, (3, 1)), COLD)
        self.assertEqual(temp_at(m, s, (4, 1)), COLD)
        self.assertFalse(m.lost(s))

    def test_demon_under_window_to_hot_outside_dies(self):
        m, s = run(['##w###',
                    '#@...#',
                    '######'], [R], t_out=HOT)
        self.assertTrue(m.lost(s))

    def test_insulated_boundary_does_nothing(self):
        m, s = run(['#######',
                    '#@.o..#',
                    '#######'], [R, R], t_out=HOT)
        self.assertEqual(temp_at(m, s, (4, 1)), NEUTRAL)


class Goal(unittest.TestCase):  # w1/level
    def test_block_on_goal_wins(self):
        m, s = run(['######',
                    '#@o*.#',
                    '######'], [R])
        self.assertTrue(m.won(s))

    def test_demon_on_goal_does_not_win(self):
        m, s = run(['#####',
                    '#@*.#',
                    '#####'], [R])
        self.assertFalse(m.won(s))

    def test_transparent_on_goal_does_not_win(self):  # w2/empty-2
        m, s = run(['######',
                    '#@t*.#',
                    '######'], [R])
        self.assertFalse(m.won(s))

    def test_hot_demon_cannot_win(self):
        m, s = run(['#######',
                    '#@o*h.#',
                    '#######'], [R])
        self.assertTrue(m.lost(s))
        self.assertFalse(m.won(s))


class Transitions(unittest.TestCase):  # w3 texts
    EMPTY = ['#####',
             '#@..#',
             '#####']

    def make(self, **levels):
        """levels: id -> (rows, links); returns a World."""
        return world.World({lid: build(rows, links=links, lid=lid) for lid, (rows, links) in levels.items()})

    def walk(self, w, h, *moves):
        for d in moves:
            h = w.step(h, d)
            self.assertIsNotNone(h)
        return h

    def body_at(self, w, h, cell):
        hit = w.current(h).occupancy(h.top).get(cell)
        return hit and hit[0]

    def test_quit_comes_out_where_it_went_in_and_resets_everything(self):  # exit-1, exit-2
        w = self.make(P=(['#######',
                          '#@.A..#',
                          '#.o...#',
                          '#######'], {'A': 'A'}),
                      A=(self.EMPTY, None))
        h = self.walk(w, w.start('P'), D, R, U)        # push o to (3,2), stand left of A
        h = w.enter(h, R)
        self.assertEqual([f.lid for f in h.path], ['P', 'A'])
        self.assertEqual(h.top.demon, (1, 1))         # inner start
        h = w.quit(h)
        self.assertEqual(h.top.demon, (2, 1))         # back where it stood when entering
        self.assertIsNotNone(self.body_at(w, h, (2, 2)))  # o is back where it started

    def test_exit_side_is_entry_side(self):  # exit-2: "离开关卡的位置和进入时相同"
        w = self.make(P=(['#######',
                          '#...A@#',
                          '#######'], {'A': 'A'}),
                      A=(self.EMPTY, None))
        h = w.quit(w.enter(w.start('P'), L))
        self.assertEqual(h.top.demon, (5, 1))

    def test_outside_temperature_follows_the_block_then_neutral(self):  # transition-3
        hot_block = ('A', mxw.Block(7, 0xaa), SOLVED)  # fixed, hot, insulated
        w = self.make(P=(['######',
                          '#@A..#',
                          '######'], {'A': hot_block}),
                      A=(['#w###',
                          '#.@.#',
                          '#####'], None))
        h = w.enter(w.start('P', t_out=HOT), R)
        self.assertEqual(h.path[-1].t_out, HOT)
        self.assertFalse(h.top.demon_temp == HOT)     # transition-1: no heat on arrival
        self.assertEqual(w.step(h, L).top.demon_temp, HOT)  # under the window to a hot outside
        h = w.quit(h)
        self.assertEqual(h.path[-1].t_out, NEUTRAL)   # the level you are now in: neutral

    def test_block_where_the_demon_comes_out_is_destroyed(self):  # transition-2
        # o starts on the cell from which the demon later enters A; exiting resets P,
        # so o is back there when the demon reappears on it
        w = self.make(P=(['######',
                          '#....#',
                          '#@.oA#',
                          '#....#',
                          '######'], {'A': 'A'}),
                      A=(self.EMPTY, None))
        h = self.walk(w, w.start('P'), U, R, R, D)     # push o down out of the way
        h = w.quit(w.enter(h, R))
        self.assertEqual(h.top.demon, (3, 2))
        self.assertEqual(sum(p is not None for p in h.top.pos), sum(
            p is not None for p in w.current(h).initial_pos) - 1)

    def test_coming_out_into_a_wall_breaks_it(self):  # transition-2, seen in the game (w3/path)
        # T: A's real block has a wall on its right and a closed room behind that wall.
        # Re-entering A through a shortcut moving left makes the exit come out on the right of
        # the real block: inside the wall, which breaks and opens the room.
        w = self.make(T=(['#######',
                          '#@.A#.#',
                          '#...#.#',
                          '#######'], {'A': 'A'}),
                      A=(['#####',
                          '#.C@#',
                          '#####'], {'C': '~A'}))
        h = w.enter(self.walk(w, w.start('T'), R), R)   # into A moving right
        h = w.enter(h, L)                               # A again, through the shortcut, moving left
        self.assertEqual(h.path[-1].dir, L)
        h = w.quit(h)
        self.assertEqual(h.top.demon, (4, 1))           # right of the real block: in the wall
        self.assertIn((4, 1), h.top.holes)
        h = w.step(h, R)                                # and on into the closed room
        self.assertEqual(h.top.demon, (5, 1))

    def test_no_heat_exchange_at_all_until_the_next_move(self):  # transition-1
        # on coming out, P is back in its initial layout, where a hot and a neutral block touch:
        # neither the demon nor those blocks exchange heat until the next move
        w = self.make(P=(['#######',
                          '#@A.ho#',
                          '#.....#',
                          '#######'], {'A': 'A'}),
                      A=(self.EMPTY, None))
        h = w.quit(w.enter(w.start('P'), R))
        m = w.current(h)
        self.assertEqual(h.top.demon, (1, 1))
        self.assertEqual(h.top.temp[m.occupancy(h.top)[(5, 1)][0]], NEUTRAL)  # not heated yet
        h = w.step(h, D)
        self.assertEqual(h.top.temp[m.occupancy(h.top)[(5, 1)][0]], HOT)      # now it is

    def test_no_heat_when_appearing_next_to_a_hot_block(self):  # transition-1
        w = self.make(P=(['#####',
                          '#@A.#',
                          '#####'], {'A': 'A'}),
                      A=(['#####',
                          '#@h.#',
                          '#####'], None))
        h = w.enter(w.start('P'), R)
        self.assertEqual(h.top.demon_temp, NEUTRAL)   # next to h, but no heat on arrival
        self.assertIsNotNone(w.quit(h))               # so it can still leave

    def test_entering_the_current_level_keeps_its_state(self):  # enter-2
        w = self.make(Q=(['#####',
                          '#.@.#',
                          '#.P.#',
                          '#####'], {'P': 'P'}),
                      P=(['#######',
                          '#@o...#',
                          '#.....#',
                          '#...S.#',
                          '#######'], {'S': '~P'}))
        h = w.enter(w.start('Q'), D)                   # into P moving down
        h = self.walk(w, h, R, D, R, D)               # o pushed to (3,1), demon left of S
        h = w.enter(h, R)                              # P again, moving right
        self.assertEqual([f.lid for f in h.path], ['Q', 'P'])  # the path does not grow
        self.assertEqual(h.top.demon, (1, 1))
        self.assertIsNotNone(self.body_at(w, h, (3, 1)))  # o stayed where it was pushed
        h = w.quit(h)
        self.assertEqual([f.lid for f in h.path], ['Q'])
        self.assertEqual(h.top.demon, (1, 2))         # Q's block (2,2), entry side of the last entry

    def test_entering_a_level_lower_on_the_path_goes_back_to_it(self):  # seen in the game
        w = self.make(H=(['#####',
                          '#@A.#',
                          '#####'], {'A': 'A'}),
                      A=(['#####',
                          '#@B.#',
                          '#####'], {'B': 'B'}),
                      B=(['#####',
                          '#@A.#',
                          '#####'], {'A': '~A'}))
        h = w.enter(w.enter(w.enter(w.start('H'), R), R), R)  # H -> A -> B -> A
        self.assertEqual([f.lid for f in h.path], ['H', 'A'])
        h = w.quit(h)                                   # leaves A, out into H
        self.assertEqual([f.lid for f in h.path], ['H'])

    def test_shortcut_into_a_deep_level_exits_through_the_real_blocks(self):  # enter-1, path
        w = self.make(T=(['#######',
                          '#@.A..#',
                          '#.....#',
                          '#...B.#',
                          '#######'], {'A': 'A', 'B': '~B'}),
                      A=(['#####',
                          '#.B@#',
                          '#####'], {'B': 'B'}),
                      B=(self.EMPTY, None))
        h = self.walk(w, w.start('T'), D, D, R, R)     # left of the shortcut to B
        h = w.enter(h, R)
        self.assertEqual([f.lid for f in h.path], ['T', 'A', 'B'])  # the real chain
        self.assertEqual([f.dir for f in h.path[1:]], [R, R])       # A skipped: shortcut's direction
        h = w.quit(h)                                   # out of B's real block in A, entry side
        self.assertEqual(([f.lid for f in h.path], h.top.demon), (['T', 'A'], (1, 1)))
        h = w.quit(h)                                   # out of A's real block in T, entry side
        self.assertEqual(([f.lid for f in h.path], h.top.demon), (['T'], (2, 1)))

    def test_level_left_for_another_keeps_its_state(self):  # enter-3
        w = self.make(A=(['#######',
                          '#@o...#',
                          '#...B.#',
                          '#######'], {'B': 'B'}),
                      B=(['#####',
                          '#@A.#',
                          '#####'], {'A': '~A'}))
        h = self.walk(w, w.start('A'), R, D, R)
        h = w.enter(w.enter(h, R), R)                  # A -> B -> back to A
        self.assertEqual([f.lid for f in h.path], ['A'])
        self.assertIsNotNone(self.body_at(w, h, (3, 1)))  # A as it was left
        self.assertEqual(h.top.demon, (1, 1))

    def test_solving_exits_and_changes_the_level_block(self):  # w1/level, goal
        w = self.make(P=(['#######',
                          '#.....#',
                          '#@.A.*#',
                          '#.....#',
                          '#######'], {'A': 'A'}),
                      A=(['######',
                          '#@o*.#',
                          '######'], None))
        h = self.walk(w, w.start('P'), R)
        h = w.enter(h, R)
        h = w.step(h, R)                               # solves A: automatic exit
        self.assertEqual([f.lid for f in h.path], ['P'])
        self.assertIn('A', h.solved)
        self.assertEqual(h.top.demon, (2, 2))         # where it stood when entering
        self.assertFalse(w.current(h).bodies[self.body_at(w, h, (3, 2))].fixed)

    def test_solver_uses_a_solved_level_block(self):
        levels = {'P': build(['#######',
                              '#.....#',
                              '#@.A.*#',
                              '#.....#',
                              '#######'], links={'A': 'A'}, lid='P'),
                  'A': build(['######',
                              '#@o*.#',
                              '######'], lid='A')}
        sv = solver.Solver(levels)
        plan, solved = sv.solve('P')
        self.assertEqual(solved, {'A', 'P'})
        self.assertTrue(solver.replay(sv, 'P', plan)[0])
        self.assertIn('[ER]', solver.flatten(plan))


S, P, I = sim.STICKY, sim.PLAIN, sim.INSULATED


class Sticky(unittest.TestCase):  # w2/sticky-1..3
    def test_sticky_face_glues_and_bodies_move_together(self):
        # block at (3,1) has a sticky right face; pushing it into (5,1)'s block glues them,
        # then pushing back from the right pulls the first block along
        faces = {(3, 1): (P, P, S, P)}
        m, s = run(['#########',
                    '#.@o.o..#',
                    '#.......#',
                    '#########'], [R], faces=faces)
        occ = m.occupancy(s)
        self.assertEqual(s.glue[occ[(4, 1)][0]], s.glue[occ[(5, 1)][0]])
        # walk round to the right side and push left: both move
        for d in (D, R, R, R, U, L):
            s = m.step(s, d)
        occ = m.occupancy(s)
        self.assertIn((3, 1), occ)
        self.assertIn((4, 1), occ)

    def test_glued_body_is_dragged_along(self):
        # two blocks side by side, glued from the start; pushing the left one down
        # drags the right one too
        faces = {(3, 2): (P, P, S, P)}
        m, s = run(['#######',
                    '#..@..#',
                    '#..oo.#',
                    '#.....#',
                    '#.....#',
                    '#######'], [D], faces=faces)
        occ = m.occupancy(s)
        self.assertIn((4, 3), occ)
        self.assertNotIn((4, 2), occ)

    def test_sticking_to_wall_makes_block_immovable(self):
        faces = {(3, 1): (P, P, S, P)}
        m, s = run(['#######',
                    '#.@o..#',
                    '#######'], [R, R], faces=faces)
        self.assertTrue(m.stuck(s, m.occupancy(s)[(5, 1)][0]))
        self.assertIsNone(m.step(s, R))

    def test_demon_does_not_stick(self):
        faces = {(3, 1): (S, P, P, P)}  # sticky face toward the demon
        m, s = run(['#######',
                    '#.@o..#',
                    '#######'], [R, L, L], faces=faces)
        self.assertEqual(s.demon, (1, 1))
        self.assertIn((4, 1), m.occupancy(s))

    def test_sticky_conducts_heat(self):  # w2/sticky-2
        faces = {(2, 1): (P, P, S, P)}
        m, s = run(['########',
                    '#@o.h..#',
                    '########'], [R], faces=faces)
        self.assertEqual(temp_at(m, s, (3, 1)), HOT)

    def test_sticky_against_insulated_face_glues_but_blocks_heat(self):
        faces = {(2, 1): (P, P, S, P), (4, 1): (I, I, I, I)}
        m, s = run(['########',
                    '#@o.h..#',
                    '########'], [R], faces=faces)
        occ = m.occupancy(s)
        self.assertEqual(s.glue[occ[(3, 1)][0]], s.glue[occ[(4, 1)][0]])
        self.assertEqual(temp_at(m, s, (3, 1)), NEUTRAL)

    def test_sticky_faces_pre_joined_in_file_are_glued_from_the_start(self):
        faces = {(3, 1): (P, P, S, P), (4, 1): (S, P, P, P)}
        m = sim.Model(build(['#######',
                             '#.@oo.#',
                             '#######'], faces))
        s = m.initial()
        occ = m.occupancy(s)
        self.assertNotEqual(occ[(3, 1)][0], occ[(4, 1)][0])  # two blocks ...
        self.assertEqual(s.glue[occ[(3, 1)][0]], s.glue[occ[(4, 1)][0]])  # ... one rigid group

    def test_destroying_one_block_of_a_glued_pair_frees_the_other(self):  # w3/transition-2
        faces = {(3, 1): (P, P, S, P), (4, 1): (S, P, P, P)}
        m = sim.Model(build(['########',
                             '#.@oo..#',
                             '########'], faces))
        s = m.destroy(m.initial(), (3, 1))
        self.assertNotIn((3, 1), m.occupancy(s))
        s = m.step(m.step(s, R), R)                   # walk up to the survivor and push it
        self.assertIn((5, 1), m.occupancy(s))
        self.assertNotIn((4, 1), m.occupancy(s))


class Transparent(unittest.TestCase):  # w2/empty-1, empty-2
    def test_isolated_transparent_block_forgets_its_heat(self):
        rows = ['######',
                '#@.t.#',
                '######']
        level = build(rows)
        level.grid[1][3] = mxw.Block(4, level.grid[1][3].sides)  # transparent but hot
        m = sim.Model(level)
        s = m.step(m.initial(), R)
        self.assertFalse(m.lost(s))
        self.assertEqual(temp_at(m, s, (3, 1)), NEUTRAL)

    def test_transparent_conducts_between_blocks(self):
        m, s = run(['########',
                    '#@o.th.#',
                    '########'], [R])
        self.assertEqual(temp_at(m, s, (3, 1)), HOT)
        self.assertEqual(temp_at(m, s, (4, 1)), HOT)  # it passes heat, it does not store it


def piston(rows, cell, side, extended, attr=2, slot=None, faces=None, prio=0):
    """A level from rows with a piston on cell (a '.' in rows): movable side towards side
    (L, D, R, U), insulated there and plain elsewhere; attr 2 neutral, 6 hot, 10 cold; slot:
    the Block inside a contracted one."""
    level = build(rows, faces)
    codes = [P] * 4
    codes[side] = I
    body = mxw.Block(attr, sum(c << (2 * i) for i, c in enumerate(codes)))
    state = int(extended) | ({U: 0, R: 1, D: 2, L: 3}[side] << 1)
    level.grid[cell[1]][cell[0]] = mxw.Piston(state, body, prio, slot)
    return sim.Model(level)


def block(faces=(P, P, P, P), attr=2):
    return mxw.Block(attr, sum(c << (2 * i) for i, c in enumerate(faces)))


class Pistons(unittest.TestCase):  # w4/piston-*, rules checked in the game
    def steps(self, m, moves):
        s = m.initial()
        for d in moves:
            s = m.step(s, d)
        return s

    def state(self, m, s, cell):
        """(extended, holds a block) of the piston on cell."""
        ext, c = s.pist[m.pindex[m.occupancy(s)[cell][0]]]
        return ext, c >= 0

    def test_hot_contracted_piston_pushes_its_block_out(self):  # piston-active-1
        m = piston(['#######',
                    '#.....#',
                    '#@....#',
                    '#######'], (3, 1), R, False, attr=6, slot=block())
        s = self.steps(m, [R])
        self.assertEqual(self.state(m, s, (3, 1)), (True, False))
        self.assertIn((4, 1), m.occupancy(s))
        self.assertEqual(s.temp[m.occupancy(s)[(3, 1)][0]], NEUTRAL)

    def test_empty_piston_extends_without_pushing(self):  # seen in the game
        m = piston(['#######',
                    '#...o.#',
                    '#@....#',
                    '#######'], (3, 1), R, False, attr=6, faces={(4, 1): (I, I, I, I)})
        s = self.steps(m, [R])
        self.assertEqual(self.state(m, s, (3, 1)), (True, False))
        self.assertIn((4, 1), m.occupancy(s))

    def test_cold_extended_piston_pulls_a_stuck_block_in(self):  # piston-active-2, seen in the game
        m = piston(['########',
                    '#...O..#',
                    '#@.....#',
                    '########'], (3, 1), R, True, attr=10, faces={(4, 1): (S, I, I, I)})
        s = self.steps(m, [R])
        self.assertEqual(self.state(m, s, (3, 1)), (False, True))
        self.assertNotIn((4, 1), m.occupancy(s))

    def test_cold_piston_with_nothing_stuck_just_contracts(self):
        m = piston(['########',
                    '#...O..#',
                    '#@.....#',
                    '########'], (3, 1), R, True, attr=10)
        s = self.steps(m, [R])
        self.assertEqual(self.state(m, s, (3, 1)), (False, False))
        self.assertIn((4, 1), m.occupancy(s))

    def test_pressing_a_block_in_heats_the_piston(self):  # piston-passive-1
        # the block goes in and the piston turns hot; it cannot push the block back out
        # while the demon stands in front and the wall is behind, so it waits
        m = piston(['######',
                    '#.@O.#',
                    '######'], (4, 1), L, True, faces={(3, 1): (I, I, I, I)})
        s = self.steps(m, [R])
        self.assertEqual(s.demon, (3, 1))
        self.assertEqual(self.state(m, s, (4, 1)), (False, True))
        self.assertEqual(s.temp[m.occupancy(s)[(4, 1)][0]], HOT)
        s = m.step(s, L)  # the way is free: the piston extends and the block comes out
        self.assertEqual(self.state(m, s, (4, 1)), (True, False))
        self.assertIn((3, 1), m.occupancy(s))

    def test_pulling_a_stuck_block_out_cools_the_piston(self):  # piston-passive-2
        # the content is stuck to the movable side and to the block in front, which is stuck
        # to the block the demon pushes up. Cold and extended, the piston contracts in the
        # same turn; the blocks cannot come back (the demon is in the way), so the piston
        # moves up over its old content instead.
        m = piston(['######',
                    '#....#',
                    '#....#',
                    '#.oo.#',
                    '#.@..#',
                    '######'], (3, 4), U, False, slot=block((I, S, I, S)),
                   faces={(3, 3): (S, S, I, I), (2, 3): (I, I, P, I)})
        s = m.initial()
        pis = m.occupancy(s)[(3, 4)][0]
        moved = m._move(s, U, [m.occupancy(s)[(2, 3)][0]])
        self.assertEqual(moved[1][m.pindex[pis]], (True, -1))  # pulled out: extended, cold
        self.assertEqual(moved[2][pis], COLD)
        s = m.step(s, U)
        self.assertEqual(s.pos[pis], (3, 3))
        self.assertEqual(self.state(m, s, (3, 3)), (False, True))
        self.assertEqual(s.temp[pis], NEUTRAL)

    def test_lower_number_acts_first(self):  # turn-2, piston priority
        # two hot empty pistons both extend, one step each, lowest number first
        level = build(['#######',
                       '#.....#',
                       '#@....#',
                       '#######'])
        hot = mxw.Block(6, sum(c << (2 * i) for i, c in enumerate((I, I, I, I))))
        level.grid[1][3] = mxw.Piston(2, hot, 1, None)
        level.grid[1][5] = mxw.Piston(2, hot, 0, None)
        m = sim.Model(level)
        s = m.step(m.initial(), R)
        self.assertEqual([e for e, _ in s.pist], [True, True])
        self.assertEqual(m.by_priority, [m.occupancy(s)[(5, 1)][0], m.occupancy(s)[(3, 1)][0]])


class SubGoals(unittest.TestCase):
    def test_goal_heuristic_and_start_hooks(self):
        levels = {'P': build(['#######',
                              '#@o..*#',
                              '#######'], lid='P')}
        sv = solver.Solver(levels)
        m = sv.model('P', frozenset(), NEUTRAL)
        bi = next(i for i, b in enumerate(m.bodies) if not b.fixed)

        def there(h):  # sub-goal: the block on (3,1)
            return bool(h.path) and h.top.pos[bi] == (3, 1)
        plan, _ = sv.solve('P', goal=there, heuristic=lambda h: 0)
        self.assertEqual(sv.last_end.top.pos[bi], (3, 1))
        rest, solved = sv.solve('P', start=sv.last_end)  # on from there to the real goal
        self.assertIn('P', solved)
        self.assertTrue(solver.replay(sv, 'P', plan + rest)[0])


class Symmetry(unittest.TestCase):
    def test_swapped_identical_blocks_give_the_same_key(self):
        m = sim.Model(build(['#######',
                             '#@o.o.#',
                             '#######']))
        s = m.initial()
        a, b = (bi for bi, x in enumerate(m.bodies) if not x.fixed)
        swapped = s._replace(pos=tuple(s.pos[b] if i == a else s.pos[a] if i == b else p
                                       for i, p in enumerate(s.pos)))
        self.assertNotEqual(s, swapped)
        self.assertEqual(m.symmetric_key(s), m.symmetric_key(swapped))

    def test_different_blocks_are_not_swapped(self):
        m = sim.Model(build(['#######',
                             '#@o.O.#',
                             '#######']))
        self.assertEqual(m.sym_classes, [])


class Pruning(unittest.TestCase):
    def h(self, rows, faces=None):
        m = sim.Model(build(rows, faces))
        return prune.Pruner().h(m, m.initial())

    def test_push_distance_in_corridor(self):
        self.assertEqual(self.h(['#######',
                                 '#@o..*#',
                                 '#######']), 3)

    def test_corner_block_is_dead(self):
        self.assertEqual(self.h(['######',
                                 '#o..*#',
                                 '#@...#',
                                 '######']), prune.INF)

    def test_push_around_corner_needs_room_for_demon(self):
        # block must go right 2 then down 1; pushing down needs the demon above it
        self.assertEqual(self.h(['######',
                                 '#....#',
                                 '#@o..#',
                                 '#...*#',
                                 '######']), 3)

    def test_other_blocks_are_ignored(self):
        # optimistic: the second block in the way does not raise the bound
        self.assertEqual(self.h(['########',
                                 '#@o.o.*#',
                                 '########']), 2)

    def test_hot_block_still_counts(self):
        self.assertEqual(self.h(['######',
                                 '#@h.*#',
                                 '######']), 2)

    def test_glue_can_make_a_block_reachable(self):  # the w2/sticky-1 situation
        # the block at (2,1) cannot be pushed onto the goal alone (walls left and above);
        # glued to the sticky-topped block below, the pair can be pushed right
        rows = ['######',
                '##o*.#',
                '#....#',
                '#.o..#',
                '#.@..#',
                '######']
        faces = {(2, 3): (P, P, P, S)}
        self.assertLess(self.h(rows, faces), prune.INF)
        sv = solver.Solver({'test': build(rows, faces)})
        plan, _ = sv.solve('test')
        self.assertTrue(solver.replay(sv, 'test', plan)[0])

    def test_fixed_block_never_counts(self):
        self.assertEqual(self.h(['######',
                                 '#@x.*#',
                                 '######']), prune.INF)


GAME = os.environ.get('MXW_GAME_DIR')


@unittest.skipUnless(GAME, 'set MXW_GAME_DIR to the game folder')
class GameData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.levels, cls.structure, cls.errors = mxw.load_world(GAME)

    def test_parser_coverage(self):
        self.assertEqual(len(self.levels), 1153)
        self.assertEqual(self.errors, {})

    # Tutorial levels the current search cannot finish quickly; checked only by catalog.py.
    KNOWN_SLOW = set()
    # Not solvable under the current rules, open question (see README).
    UNRESOLVED = set()
    # Tutorial levels only solvable in the context they are met in.
    CONTEXT = {'8d2fdcfc': dict(solved=frozenset({'394c69e4'}), t_out=COLD),  # via a cold block
               'b0e93052': dict(scope='1bfecdfb'),  # only met inside 1bfecdfb
               '9de258d5': dict(scope='0d33f295'),  # w3/path: needs walls of 0d33f295 broken
               '601b40f2': dict(scope='0d33f295')}

    def test_tutorial_levels_solve_and_replay(self):
        from mdemon import catalog
        for world in ('w1', 'w2', 'w3'):
            for kind, lid in catalog.world_levels(self.structure, self.levels, world):
                if kind != 'hint' or not any(t[2].startswith(world + '/') for t in self.levels[lid].texts):
                    continue
                if lid in self.KNOWN_SLOW or lid in self.UNRESOLVED:
                    continue
                ctx = self.CONTEXT.get(lid, {})
                with self.subTest(level=lid):
                    r = solver.solve_any(self.levels, lid, 30, **ctx)  # any plan will do here
                    self.assertIsNotNone(r)
                    sv, plan, _ = r
                    self.assertTrue(solver.replay(sv, lid, plan, **ctx)[0])

    def test_derived_layout_solves_w1_15(self):
        # the shuffle level: cooling layout and stage order derived backwards from the goal
        from mdemon import derive
        d = derive.Derivation(self.levels, '4b1153be', 30, log=lambda *a: None)
        plan = d.solve()
        self.assertIsNotNone(plan)
        self.assertTrue(solver.replay(d.staged.sv, '4b1153be', plan)[0])

    def test_context_levels_need_their_context(self):
        sv = solver.Solver(self.levels, time_budget=30)
        for lid in self.CONTEXT:
            with self.subTest(level=lid):
                self.assertIsNone(sv.solve(lid))  # on its own, with a neutral outside: no way


if __name__ == '__main__':
    unittest.main()
