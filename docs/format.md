# 游戏数据格式

游戏目录下的 `world/` 里有 1153 个 `*.mxw` 关卡文件和一个 `structure.json`（关卡树），`languages/*.json` 是各语言的文本（其中 `hint` 段是各世界教程关的规则说明，中文版 `zh-CN.json` 的措辞最准确）。解析器是 `mdemon/mxw.py`，全部 1153 个文件都能完整解析。

## .mxw 关卡文件

```
u8 W, u8 H
W*H 个格子对象（按行）
尾部: u8 目标数, 目标 (i8 x, i8 y)...;  { 02 x y 文本键\0 }...;  00
```

目标可以在网格外（比如 `-1`）。尾部的文本键对应 `languages/*.json` 里 `hint` 段的教程文字。

| tag | 对象 |
|---|---|
| `00` | 空 |
| `01` | 恶魔起点 |
| `02 attr sides` | 方块 |
| `03 flag id\0 未解对象 已解对象` | 关卡块；flag 1 = 真关卡块，0 = 捷径（见 [rules.md](rules.md)） |
| `04 state 机身 优先级 [活动面]` | 活塞；state bit0=0（伸出）时才有活动面对象 |
| `05 attr sides x y` | 活塞头的变体（共 5 字节，后两字节含义待查） |

- **attr**：bit0 固定钉，bit1 储热（0 = 透明），bit2 热，bit3 冷，bit2+bit3 = 第四温度
- **sides**：每面 2 位，顺序 左、下、右、上；0 = 粘性（导热），1 = 导热，2 = 绝热。墙体和多格方块内部，就是两两相对的粘性面
- 墙体里混着带钉（`B3xx`）和不带钉（`B2xx`）的格子；含有固定格的整块墙在模型里是一个物体
- 由网格边界相连的固定墙体代表"外界"，带导热面的墙格就是通向外界的窗口

tag `05` 的长度最初按 4 字节解析，有 4 个文件因此错位、解析失败；后来参照第三方关卡编辑器 [MatttNguyen/mpd-leditor](https://github.com/MatttNguyen/mpd-leditor) 的 `scripts/level_dat.gd` 改成 5 字节，就全部能解析了。该编辑器里其余对象的长度，和我们逆向出来的完全一致。

## structure.json 关卡树

每个节点有 `normalSublevels`（数字关）、`extraSublevels`（字母关）、`metaSublevels`（希腊字母的元关卡）、`hintSublevels`（提示关）。

- 世界节点：w1 = `9a498c50`，w2 = `6c1848b0`，w3 = `214a0e55`（`mdemon/catalog.py` 的 `WORLDS`）。游戏里的编号按树里的顺序：数字关 1, 2, …，字母关 A, B, …（`catalog.numbered`）。
- 提示关下面挂的子关，几乎都是提示关地图上真实摆着的关卡块（走过去进入，不是按 H）：360 个里有 359 个是这样（`tools/explore/mxw_nested_hints.py`）。唯一的例外 `a7674929` 在全游戏里都没有入口，是遗留的废弃数据，批量求解时跳过。
- 真关卡块（flag 1）共 901 个，全部放在树里给出的上一级关卡中（`tools/explore/mxw_real_blocks.py`）。

## 内部 id 和游戏里的位置

内部 id 是 8 位十六进制，游戏界面里看不到。`scripts/where_is.py <游戏目录> <id>` 会给出游戏里的进入路径（世界、第几关、关卡块在第几行第几列、旁边的提示文字）和关卡地图。
