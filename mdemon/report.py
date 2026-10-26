"""Step-by-step walkthroughs of plans, for trying them in the game."""
from . import mxw, sim, solver

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


