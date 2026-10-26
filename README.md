# Maxwell's puzzling demon 求解器

给解谜游戏 *Maxwell's puzzling demon* 写的关卡解析器、规则模拟器和求解器。目前覆盖 w1 到 w3 的机制：推动、热交换、粘性面、透明块，以及关卡的进入、退出和嵌套。生成的解法在游戏里实测都成立。

## 目录结构

```
mdemon/            核心库
  mxw.py             关卡文件格式（world/*.mxw、structure.json）
  sim.py             单个关卡内的规则：推动、粘连、销毁、热交换、胜负
  world.py           关卡之间的规则：进入路径、进出关卡、重置、外界温度
  prune.py           静态推动距离表、启发值（可采纳的和引导式的）、死局剪枝
  solver.py          A* 搜索、solve_any、回放
  catalog.py         世界和关卡列表
  staged.py          分阶段子目标搜索
  derive.py          自动推导腾挪关的终局布局和阶段顺序
  report.py          分步攻略输出
  context.py         从上一级关卡里"刚进入"的状态开始求解
scripts/           命令行工具（见下）
tools/explore/     逆向文件格式和调查个别关卡时用的一次性脚本
tests/test_sim.py  规则测试 + 游戏数据测试
docs/              详细文档
logs/              批量求解和实验的日志
solutions/         分步攻略
```

## 常用命令

下面的 `<游戏目录>` 是游戏安装目录，例如 `D:\Program Files (x86)\Steam\steamapps\common\Maxwell's puzzling demon`。

日常验证：不设 `MXW_GAME_DIR` 时只跑规则测试，不到 1 秒；设了以后会加上解析覆盖率检查、w1–w3 全部教程关的求解与回放，以及 w1 第 15 关的自动推导，约 65 秒。

```bash
python -m unittest discover -s tests
```

| 用途 | 命令 |
|---|---|
| 查某个内部 id 在游戏里的位置和地图 | `python scripts/where_is.py <游戏目录> <id>` |
| 生成一关的分步攻略 | `python scripts/show_solution.py <游戏目录> <id> [秒数]` |
| 求解单关（可指定上一级作为范围） | `python scripts/solve_one.py <游戏目录> <秒数> <id>[@上一级id] ...` |
| 只跑某个世界的教程关 | `python -u scripts/run_tutorials.py <游戏目录> w3 15` |
| 批量求解一个世界 | `python -u scripts/run_world.py <游戏目录> w2 cell 60` |
| 批量求解字母关 | `python -u scripts/run_extras.py <游戏目录> 60` |
| 分阶段子目标求解 | `python -u scripts/subgoal.py <游戏目录> <id> 30 体@x,y:C / ...` |
| 自动推导腾挪关 | `python -u scripts/derive.py <游戏目录> <id> 30 --out <文件>` |
| 逐步回放解法 | `python scripts/trace_plan.py <游戏目录> <id>` |
| 对比搜索配置 | `python scripts/bench.py <游戏目录> <秒数> <id> ...` |
| 看关卡网格 / 关卡树 | `python scripts/show_level.py <游戏目录> <id>`，`python scripts/show_tree.py <游戏目录> <深度> <id>` |
| 搜索开销统计 / 性能分析 | `scripts/search_stats.py`，`scripts/prof_solver.py` |
| 某关真关卡块周围 / 恶魔能走到哪 | `scripts/near_block.py`，`scripts/map_reach.py` |

批量求解很耗时，在后台跑并把日志写进 `logs/`。

## 文档

- [docs/format.md](docs/format.md)：游戏数据格式、关卡树、内部 id
- [docs/rules.md](docs/rules.md)：规则模型（单关内、关卡之间）、游戏内实测纠正过的规则、待确认的假设
- [docs/search.md](docs/search.md)：A*、剪枝、引导式搜索、分阶段子目标、自动推导
- [docs/results.md](docs/results.md)：实测通过的解法、教程关、批量结果、字母关和 w3-H
