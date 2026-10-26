"""Solve a level and print it in a form that is easy to try in the game.

Usage: show_solution.py GAME_DIR LEVEL [seconds, default 60]
Prints the starting map, then the moves in groups of 5 with arrows, each group followed by the
map after it, so a mismatch in the game can be found quickly.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mxw, sim, solver

ARROW = {'L': '←', 'D': '↓', 'R': '→', 'U': '↑'}
LEGEND = ('# 墙  @ 恶魔(& = 被烫)  o 中性块  H 热块  C 冷块  t 透明块  '
          'x 固定块  L 关卡块  * 目标')


def walkthrough(sv, lid, plan, out=print):
    """Print plan (moves only, no level entries) step by step from the level's start."""
    moves = solver.flatten(plan)
    if any(ch not in ARROW for ch in moves):
        raise ValueError(f'plan enters levels, not supported here: {moves}')
    w = sv.world
    h = w.start(lid)
    out(LEGEND)
    out(f'\n关卡 {lid}，共 {len(moves)} 步。开始时：')
    out(w.current(h).render(h.top))
    for i in range(0, len(moves), 5):
        chunk = moves[i:i + 5]
        for letter in chunk:
            h = w.step(h, sim.DIR_NAMES.index(letter))
        arrows = ' '.join(ARROW[c] for c in chunk)
        out(f'\n第 {i + 1}-{i + len(chunk)} 步：{arrows}')
        out('过关！' if not h.path else w.current(h).render(h.top))


if __name__ == '__main__':
    levels = mxw.load_world(sys.argv[1])[0]
    lid = sys.argv[2]
    budget = float(sys.argv[3]) if len(sys.argv) > 3 else 60
    sv, plan, _ = solver.solve_any(levels, lid, budget)
    assert solver.replay(sv, lid, plan)[0], 'plan does not replay'
    walkthrough(sv, lid, plan)
