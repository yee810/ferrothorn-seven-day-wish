# 运行时素材目录

这里仅保存《坚果矿洞大冒险：七日与千年的心愿》运行及地图/事件编辑所需的资源。

```text
resource/
|-- audio/
|   |-- bgm/              地图、战斗与剧情背景音乐
|   |-- cries/            当前三只敌方宝可梦叫声
|   `-- se/               UI、伤害和技能音效
|-- battle/
|   |-- backgrounds/      树林龟与矿洞战斗场景
|   |-- effects/          已接入的招式动画表
|   |-- pokemon/          当前战斗所需正背面精灵
|   `-- ui_gen3_2x/       480x320 战斗 UI 拆件
|-- dialogue/
|   |-- pokemons/         树林龟战斗立绘
|   `-- preloads/         已合成的对话覆盖层
|-- event/icon/           地图事件图标
|-- fonts/                游戏字体
|-- granite_cave/         旧剧情场景的洞穴背景兼容资源
|-- map/
|   |-- characters/       地图角色备用精灵
|   |-- effects/          陨石扬尘等地图动画
|   |-- objects/          岩石破坏动画
|   `-- tilesets/         地图编辑器使用的洞穴图块表
`-- Meteor/               陨石动画帧
```

地图成品位于 `assets/maps`，事件配置位于 `assets/map_events.json`，树林龟教学战配置位于 `assets/battles/grotle_tutorial.json`。不要把临时截图、逐格切片或预览导出放回本目录；战斗预览输出目录已由 `.gitignore` 忽略。
