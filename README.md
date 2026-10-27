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
| 解法库：每关最优解和游戏内验证情况 | `python scripts/solutions.py list [w4]` |
| 在游戏里通过后标记 | `python scripts/solutions.py verify w4-16` |
| 导出 TAS 脚本（见下） | `python scripts/solutions.py tas w4-16` |
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

## 解法库和 TAS

`solve_one.py`、`run_world.py`、`run_tutorials.py`、`run_extras.py`、`show_solution.py`、`bench.py` 解出并回放成功的解法，都会自动存进 `solutions/db.json`（`mdemon/store.py`）。同一关的所有不同解法都会保留下来，步数最少的就是最优解。在游戏里照着走通以后，用 `solutions.py verify` 标记，标记跟着那一条具体的解法走；以后找到更短的解时，列表会显示"旧解已通过，最优解未验证"。

`solutions.py tas` 把最优解导出成 [WYXkk/Maxwell-s-TAS-demon](https://github.com/WYXkk/Maxwell-s-TAS-demon) 的脚本，放在 `solutions/tas/`。它会在规则模拟里回放一遍，每次有活塞额外动作就补一个 `p`，过关后补 `-`。脚本从关卡起点开始，所以要先手动进入关卡。用法：用 C++ 编译器编译那个项目的 `tas.cpp`，旁边放一个写着各按键等待时间的 `interval.txt`（格式见它的 README），运行后输入脚本路径，3 秒内切回游戏窗口；按住 `t` 可以中途停止。含进入关卡的解法里，`e` 的朝向还没核对过。

## GitHub 上的相关项目（2026-10 查询）

目前没有找到其他求解器，相关的项目有这些：

| 项目 | 内容 | 对本项目的价值 |
|---|---|---|
| [MatttNguyen/mpd-leditor](https://github.com/MatttNguyen/mpd-leditor) | 关卡编辑器（Godot），能读写 `.mxw` | 它的 `level_dat.gd` 让我们修正了 tag `05` 的长度，全部 1153 个关卡文件都能解析了 |
| [azaaz-1/CustomizableSokoban](https://github.com/azaaz-1/CustomizableSokoban) | Godot / C# 复刻，含活塞（`Piston.cs`）、热传导、推动规则 | 做 w4 活塞时可以参考它对活塞嵌套、粘性的处理 |
| [WYXkk/Maxwell-s-TAS-demon](https://github.com/WYXkk/Maxwell-s-TAS-demon) | TAS 工具：把 `wasd`/`e`/`q` 文本按时间间隔发给游戏 | 可以把求解器的解法直接导出成它的脚本，自动在游戏里回放验证 |
| [Jorrrmungandr/maxwells-puzzling-demon](https://github.com/Jorrrmungandr/maxwells-puzzling-demon) | Web 版复刻（TypeScript），实现了推动和冷热传导 | 参考价值有限 |
| [qiekn/maxwells-puzzling-demon](https://github.com/qiekn/maxwells-puzzling-demon) | Unity 复刻练习，已停更 | 参考价值有限 |

## 文档

- [docs/format.md](docs/format.md)：游戏数据格式、关卡树、内部 id
- [docs/rules.md](docs/rules.md)：规则模型（单关内、关卡之间）、游戏内实测纠正过的规则、待确认的假设
- [docs/search.md](docs/search.md)：A*、剪枝、引导式搜索、分阶段子目标、自动推导
- [docs/results.md](docs/results.md)：实测通过的解法、教程关、批量结果、字母关和 w3-H
