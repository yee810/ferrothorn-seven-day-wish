# 坚果矿洞大冒险：七日与千年的心愿

不管你是出自什么原因点进这个项目读到我的文本，我都要先告诉你，这首先是一个单片机设计期末作业，然后才是一个游戏。

最佳的体验方式：使用适配的stc学习板当作游戏的控制器，通过小板上的多传感器联动游戏内的交互。

不过在我码下这行字的时候，这样体验过的人一只手就能数的过来。甚至明天连我本人的板子也要上交，没有机会再体验了。

那至少用键盘也能玩不是吗，但唯一我尚且满意的创新点如此也只能怀念了，为醋包的饺子结果醋撒了，大概就是这种感觉。

而且原本很简单的战斗环节也会因为没有数值的增幅变得超级粪（小更新了一下，现在也还能玩了），剩下纯ai写的代码和我本人拼尽全力拉出来的剧情，可谓是集百家之所短。

能看到这里还没有叉掉页面，难道说你真的想玩我的游戏吗，那请遵循后面ai生成的引导教程吧。

总之，这是一款使用 Python/Pygame 制作的第三世代宝可梦风格 RPG，也是 STC-B 学习板创新设计课程项目。
玩家控制刚刚进化的坚果哑铃穿过矿洞寻找坠落的星星，并与超音蝠、可可多拉、勾魂眼和神秘角色相遇。光照和震动传感器会直接影响战斗技能与地图能力。

## 快速开始

推荐使用 Windows 和 Python 3.12。首次运行：

```powershell
git clone https://github.com/qingjiaofu-boop/poke.git
cd poke
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python adventure.py
```

以后可直接激活环境并运行 `python adventure.py`，也可以双击根目录的 `run.bat`。

连接 STC-B 时，把 Windows 分配的串口号作为参数：

```powershell
python adventure.py COM3
```

## 操作

| 键盘 | STC-B | 功能 |
| --- | --- | --- |
| 方向键 | 导航键 | 地图移动、菜单选择 |
| `Enter` | 导航中键/K1 | 对话快进、确认技能 |
| `Z` | 震动事件 `0x09` | 使用重磅冲撞 |
| `R` | K2 `0x06` | 重置流程或战斗 |
| `Esc` | - | 退出游戏 |

调试期间还可以按数字键 `1` 到 `5` 查看世界地图和四层矿洞。

## 游戏内容

战斗现已按纯键盘、零光照重新平衡：加入生长、守住、招式附加效果和对手下一招预告。玩法建议、数值位置和传感器范围见 [战斗规则与策略](docs/BATTLE_BALANCE.md)。

战斗显示实际伤害，Enter／导航中键可快进技能动画。勾魂眼战保留四个常规技能，并有可探索的隐藏招式与败北提醒。

- 480x320 逻辑分辨率，窗口以 2 倍最近邻方式显示。
- 室外世界与 `grancave`、`caveB1F`、`caveB2f`、`finalcave` 四张洞穴地图。
- 32x32 原子步移动、三层地图、碰撞、双向楼梯传送与可破坏岩石。
- 开幕进化、树林龟教学战、三场矿洞事件战和基拉祈终章。
- 对话立绘、逐字显示、镜头移动、动画、剧情标记和一次性事件。
- 光照传感器控制日光束威力与光合作用回复量。
- 震动传感器在战斗中触发重磅冲撞，在地图上击碎岩石。

## 背景音乐

| 场景 | 曲目 |
| --- | --- |
| 四张洞穴地图 | `1-25. Petalburg Woods ~ Granite Cave ~ Jagged Pass ~ Fiery Path.flac` |
| 战斗 | `1-09. Battle! (Wild Pokémon).flac` |
| 基拉祈终章开场 | `70. Don't Ever Forget....flac` |
| 七日回忆开始 | `62. Through the Sea of Time.flac` |

## 项目结构

```text
poke/
|-- adventure.py              正式游戏入口
|-- essentials_adventure.py   地图、事件、战斗和渲染主循环
|-- event_system.py           剧情事件数据模型
|-- scripted_battle.py        树林龟脚本化教学战
|-- battle_demo.py            三场矿洞战斗的独立测试入口
|-- sensor_monitor.py         STC-B 原始串口数据监视器
|-- assets/
|   |-- maps/                 三层地图和世界连接配置
|   |-- battles/              脚本化战斗配置
|   `-- resource/             运行时图像、字体与音频
|-- tools/                    地图、事件和世界地图编辑工具
|-- tests/                    回归测试
|-- scripts/                  可选批处理启动脚本
|-- firmware/                 STC-B Keil 工程与可烧录 HEX
`-- docs/                     开发说明
```

根目录只保留正式入口和它直接依赖的核心模块。地图数据、战斗资源、对话资源和音频分别放在自己的子目录中。

## 独立战斗测试

不进入主线即可测试超音蝠、可可多拉和勾魂眼三场战斗：

```powershell
python battle_demo.py
python battle_demo.py --port COM3
```

数字键 `1`、`2`、`3` 切换战斗。方向键选择技能，`Enter` 确认；勾魂眼战选中重磅冲撞后必须按 `Z` 或敲击学习板。

对应战斗数值说明位于：

- `assets/resource/battle/battle_with_zubat.txt`
- `assets/resource/battle/battle_with_aron.txt`
- `assets/resource/battle/battle_with_sableye.txt`

树林龟教学战配置位于 `assets/battles/grotle_tutorial.json`。更多串口与战斗流程说明见 [docs/STC_BATTLE_FLOW.md](docs/STC_BATTLE_FLOW.md)。

## STC-B 固件

开发板工程位于 `firmware/stc_bsp_gomoku`，可直接烧录的文件是：

```text
firmware/stc_bsp_gomoku/output/STC_BSP_Gomoku.hex
```

串口使用 9600 baud，协议如下：

| 数据 | 含义 |
| --- | --- |
| `0x01` 到 `0x04` | 上、下、左、右 |
| `0x05` | 确认 |
| `0x06` | 重置 |
| `0x09` | 震动事件 |
| `0x40 hi lo` | 光照 ADC |
| `0x41 hi lo` | 温度 ADC |

烧录与连线说明见 [firmware/README.md](firmware/README.md)。只查看开发板原始数据时运行：

```powershell
python sensor_monitor.py COM3
```

## 编辑地图

```powershell
python tools/map_editor.py grancave
```

地图编辑器读取 `assets/Outside.png` 和 `assets/resource/map/tilesets/granite_tiles_32.png`。它支持三层绘制、碰撞格、出生点、区域复制和事件图标预览。保存后会更新 `assets/maps` 中的三张图层 PNG 与 `outdoor_maps.json`。

修改室外子地图后，重新烘焙 120x120 世界地图：

```powershell
python tools/build_world_map.py
```

## 编辑事件

```powershell
python tools/event_editor.py
```

剧情统一保存在 `assets/map_events.json`。编辑器支持：

- 踩格、游戏开始、传送尝试、传送到达和岩石破坏触发器。
- 对话、战斗、提示、标记、等待、镜头、动画、角色移动和岩石破坏步骤。
- 从 `assets/resource/audio/bgm` 选择音乐的 `play_music` 步骤。
- 480x320 对话预览与文字渐入效果。

对白渐入时按一次确认会立即显示全文；全文已经显示时，再按一次进入下一步骤。

## 回归测试

测试统一放在 `tests`：

```powershell
python tests/test_event_system.py
python tests/test_scripted_battle.py
python tests/test_battle_demo.py
python tests/test_adventure.py
python tests/test_sensor_monitor.py
```

## 素材说明

运行时素材已按用途整理在 `assets/resource`，目录说明见 [assets/resource/README.md](assets/resource/README.md)。项目使用了 Pokémon Essentials/GBA 风格参考素材及宝可梦相关素材，仅用于课程作业与学习展示。
