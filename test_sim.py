"""Rule tests for sim.py, one group per w1 tutorial text. Run: python -m unittest test_sim

Levels are drawn in a small ASCII language:
    #  fixed boundary wall (insulated toward the room)   w  boundary wall with a conductive face
    .  floor        *  goal        @  demon start
    o  neutral block   h  hot block   c  cold block      (conductive on all sides)
    O  insulated neutral block   x  fixed neutral block
    t  transparent block
Set MXW_GAME_DIR to also run the data tests against the installed game.
"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mxw, prune, sim, solver
from sim import HOT, COLD, NEUTRAL

L, D, R, U = range(4)
ATTR = {'o': 2, 'h': 6, 'c': 10, 'O': 2, 'x': 3, 't': 0, '#': 3, 'w': 3}


def build(rows, faces=None):
    """faces: {(x, y): (left, down, right, up)} overrides for single blocks."""
    h, w = len(rows), len(rows[0])
    grid, goals = [], []
    for y, row in enumerate(rows):
        line = []
        for x, ch in enumerate(row):
            if ch in '.*':
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
    return mxw.Level('test', w, h, grid, goals)


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
        self.assertEqual(occ[(4, 1)][0], occ[(4, 2)][0])

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

    def test_sticky_faces_pre_joined_in_file_are_one_body(self):
        faces = {(3, 1): (P, P, S, P), (4, 1): (S, P, P, P)}
        m = sim.Model(build(['#######',
                             '#.@oo.#',
                             '#######'], faces))
        occ = m.occupancy(m.initial())
        self.assertEqual(occ[(3, 1)][0], occ[(4, 1)][0])


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
        self.assertGreaterEqual(len(self.levels), 1149)
        self.assertLessEqual(set(self.errors), {'16fa52fc', '5aa8419e', '7960b275', '88abb570'})

    # Tutorial levels the current search cannot finish quickly; checked only by run_world.py.
    KNOWN_SLOW = {'eadb3d02'}  # w1/insulated-2

    def test_tutorial_levels_solve_and_replay(self):
        import run_world
        sv = solver.Solver(self.levels, time_budget=30)
        for world in ('w1', 'w2'):
            for kind, lid in run_world.world_levels(self.structure, self.levels, world):
                if kind != 'hint' or not any(t[2].startswith(world + '/') for t in self.levels[lid].texts):
                    continue
                if lid in self.KNOWN_SLOW:
                    continue
                with self.subTest(level=lid):
                    r = sv.solve(lid)
                    self.assertIsNotNone(r)
                    self.assertTrue(solver.replay(sv, lid, r[0])[0])


if __name__ == '__main__':
    unittest.main()
