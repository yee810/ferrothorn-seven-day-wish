"""Standalone Ferrothorn battle encounter UI prototype.

The renderer uses a 480x320 logical canvas (2x the GBA resolution) and only
integer nearest-neighbour scaling for the desktop window. Battle values live
in ENCOUNTERS below; matching design notes live in assets/resource/battle. This
prototype deliberately has no levels, experience, or PP system.
"""

from __future__ import annotations

import argparse
import math
import os
import queue
import random
import sys
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BATTLE_ASSETS = ROOT / "assets" / "resource" / "battle"
UI_ASSETS = BATTLE_ASSETS / "ui_gen3_2x"
AUDIO_ASSETS = ROOT / "assets" / "resource" / "audio"

LOGICAL_SIZE = (480, 320)
DEFAULT_WINDOW_SCALE = 2
FPS = 60
STC_UP_COMMAND = 0x01
STC_DOWN_COMMAND = 0x02
STC_LEFT_COMMAND = 0x03
STC_RIGHT_COMMAND = 0x04
STC_CONFIRM_COMMAND = 0x05
STC_RESET_COMMAND = 0x06
STC_VIBRATION_COMMAND = 0x09
STC_LIGHT_MARKER = 0x40
STC_TEMPERATURE_MARKER = 0x41
STC_CONTROL_COMMANDS = frozenset(
    (
        STC_UP_COMMAND,
        STC_DOWN_COMMAND,
        STC_LEFT_COMMAND,
        STC_RIGHT_COMMAND,
        STC_CONFIRM_COMMAND,
        STC_RESET_COMMAND,
        STC_VIBRATION_COMMAND,
    )
)

FOE_BOX_RECT = (6, 8, 192, 68)
PLAYER_BOX_RECT = (280, 146, 200, 68)
MESSAGE_POS = (0, 228)
MOVE_LIST_POS = (0, 220)
MOVE_INFO_POS = (324, 220)

TEXT_COLOR = (48, 48, 40)
MESSAGE_COLOR = (248, 248, 248)
INFO_COLOR = (56, 56, 56)


@dataclass(frozen=True)
class MoveSpec:
    name: str
    category: str
    value_label: str
    damage: int = 0
    damage_max: int | None = None
    damage_scale: float = 1.0
    heal_percent: int = 0
    effect: str = "attack"
    info_lines: tuple[str, str] | None = None
    trigger: str = "confirm"
    light_min: int | None = None
    light_max: int | None = None
    accuracy: int = 100
    high_crit: bool = False
    secondary: str = ""


@dataclass(frozen=True)
class EncounterSpec:
    key: str
    number: int
    enemy_name: str
    enemy_max_hp: int
    background: str
    player_moves: tuple[MoveSpec, ...]
    foe_moves: tuple[MoveSpec, ...]
    opening_notes: tuple[str, ...] = ()
    foe_moves_first: bool = False
    hidden_move: MoveSpec | None = None


class STCSerialBridge:
    """Read the STC-B byte protocol and forward raw events to the battle UI."""

    def __init__(self, port: str | None, on_event):
        self.port = port
        self.on_event = on_event
        self.stop = threading.Event()
        self.link = None
        self.status = "键盘模式"
        self.marker = None
        self.high = None

    def start(self):
        if not self.port:
            return
        try:
            import serial
            self.link = serial.Serial(self.port, 9600, timeout=0.2)
            self.status = f"串口已连接：{self.port}"
        except Exception as exc:
            self.status = f"串口连接失败：{exc}"
            return
        threading.Thread(target=self._read_loop, daemon=True).start()

    def _read_loop(self):
        while not self.stop.is_set() and self.link:
            data = self.link.read(64)
            for value in data:
                self._handle_byte(value)

    def _handle_byte(self, value: int) -> None:
        if self.marker is None and value in (STC_LIGHT_MARKER, STC_TEMPERATURE_MARKER):
            self.marker, self.high = value, None
        elif self.marker is not None:
            if self.high is None:
                self.high = value
            else:
                raw = (self.high << 8) | value
                kind = "light" if self.marker == STC_LIGHT_MARKER else "temperature"
                self.on_event(kind, raw)
                self.marker, self.high = None, None
        elif value in STC_CONTROL_COMMANDS:
            self.on_event("command", value)

    def close(self):
        self.stop.set()
        if self.link:
            self.link.close()


GROWTH = MoveSpec("生长", "变化", "攻击/特攻↑", effect="growth",
                  info_lines=("攻击、特攻升一级", "最多提升六级"))
PROTECT = MoveSpec("守住", "变化", "抵挡下次攻击", effect="protect",
                   info_lines=("抵挡下次攻击", "连续使用易失败"))
HEAVY_SLAM = MoveSpec("重磅冲撞", "物理", "", damage=50, damage_max=59,
                      effect="heavy", trigger="vibration",
                      info_lines=("双方体重相差越大", "威力越高"))
SABLEYE_DEFEAT_HINT = "勾魂眼：咦，你不是从可可多拉那里学了一招吗，怎么不对老夫用？"

ZUBAT_PLAYER_MOVES = (
    MoveSpec(
        "日光束", "特殊", "威力：70", damage=24, damage_max=28,
        effect="solar", light_min=70, light_max=120,
    ),
    MoveSpec(
        "光合作用", "变化", "回复量：30%", heal_percent=30,
        effect="synthesis", light_min=30, light_max=50,
    ),
    GROWTH, PROTECT,
)

ZUBAT_FOE_MOVES = (
    MoveSpec("翅膀攻击", "物理", "", damage=19, damage_max=23, effect="attack"),
    MoveSpec("画龙点睛", "物理", "", damage=30, damage_max=35, effect="tackle", secondary="defenses_down"),
    MoveSpec("杂技", "物理", "", damage=12, damage_max=14, effect="tackle", secondary="acrobatics"),
)


ARON_PLAYER_MOVES = (
    MoveSpec(
        "日光束", "特殊", "威力：70", damage=33, damage_max=40,
        effect="solar", light_min=70, light_max=120,
    ),
    MoveSpec(
        "光合作用", "变化", "回复量：30%", heal_percent=30,
        effect="synthesis", light_min=30, light_max=50,
    ),
    GROWTH, PROTECT,
)

ARON_FOE_MOVES = (
    MoveSpec("岩崩", "物理", "", damage=16, damage_max=20, effect="rock", accuracy=90, secondary="flinch"),
    MoveSpec("彗星拳", "物理", "", damage=20, damage_max=24, effect="heavy", accuracy=90, secondary="attack_up"),
    MoveSpec("尖石攻击", "物理", "", damage=25, damage_max=30, effect="rock", accuracy=80, high_crit=True),
)

SABLEYE_PLAYER_MOVES = (
    MoveSpec(
        "日光束", "特殊", "威力：40", damage=16, damage_max=19,
        effect="solar", light_min=40, light_max=80,
    ),
    MoveSpec(
        "光合作用", "变化", "回复量：20%", heal_percent=20,
        effect="synthesis", light_min=20, light_max=40,
    ),
)

SABLEYE_FOE_MOVES = (
    MoveSpec("暗袭要害", "物理", "", damage=24, damage_max=28, effect="attack", high_crit=True),
    MoveSpec("移花接木", "物理", "", damage=44, damage_max=50, effect="heavy", secondary="foul_play"),
    MoveSpec("暗影爪", "物理", "", damage=24, damage_max=28, effect="tackle", high_crit=True),
)


def clamp_light(raw: int | None) -> int:
    """Keep the board's reported light value in the requested 0..105 range."""
    return max(0, min(105, 0 if raw is None else int(raw)))


def light_value(raw: int | None, minimum: int, maximum: int) -> int:
    """Map the board's 0..105 light range onto inclusive gameplay values."""
    return minimum + round(clamp_light(raw) * (maximum - minimum) / 105)


def light_solar_power(raw: int | None, minimum: int = 70, maximum: int = 120) -> int:
    return light_value(raw, minimum, maximum)


def light_synthesis_percent(raw: int | None, minimum: int = 30, maximum: int = 50) -> int:
    return light_value(raw, minimum, maximum)


def light_adjusted_move(move: MoveSpec, raw: int | None) -> MoveSpec:
    """Apply this encounter's light limits without changing its base damage roll."""
    if move.effect == "solar":
        minimum = 70 if move.light_min is None else move.light_min
        maximum = 120 if move.light_max is None else move.light_max
        power = light_solar_power(raw, minimum, maximum)
        return replace(
            move,
            value_label=f"威力：{power}",
            damage_scale=power / minimum,
        )
    if move.effect == "synthesis":
        minimum = 30 if move.light_min is None else move.light_min
        maximum = 50 if move.light_max is None else move.light_max
        percent = light_synthesis_percent(raw, minimum, maximum)
        return replace(move, value_label=f"回复量：{percent}%", heal_percent=percent)
    return move

ENCOUNTERS = {
    "zubat": EncounterSpec(
        "zubat", 1, "超音蝠", 100, "rocky", ZUBAT_PLAYER_MOVES, ZUBAT_FOE_MOVES,
        foe_moves_first=True,
    ),
    "aron": EncounterSpec(
        "aron",
        2,
        "可可多拉",
        204,
        "rocky_eve",
        ARON_PLAYER_MOVES,
        ARON_FOE_MOVES,
        foe_moves_first=True,
    ),
    "sableye": EncounterSpec(
        "sableye",
        3,
        "勾魂眼",
        280,
        "rocky_eve",
        (GROWTH, PROTECT, *SABLEYE_PLAYER_MOVES),
        SABLEYE_FOE_MOVES,
        (
            "矿洞底层光线较弱，日光束和光合作用效果变差。",
        ),
        hidden_move=HEAVY_SLAM,
    ),
}

class EncounterBattleRules:
    """Small battle rules layer that can be tested without Pygame."""

    def __init__(
        self,
        encounter: EncounterSpec | str = "zubat",
        rng: random.Random | None = None,
    ) -> None:
        if isinstance(encounter, str):
            encounter = ENCOUNTERS[encounter]
        self.encounter = encounter
        self.player_max_hp = 149
        self.foe_max_hp = encounter.enemy_max_hp
        self.player_hp = self.player_max_hp
        self.foe_hp = self.foe_max_hp
        self.rng = rng or random.Random()
        self.player_attack = 0
        self.player_sp_attack = 0
        self.foe_attack = 0
        self.foe_defense = 0
        self.foe_sp_defense = 0
        self.protected = False
        self.protect_chain = 0
        self.flinched = False
        self.foe_turn = 0
        self.last_message = ""
        self.last_effect = ""
        self.heavy_slam_used = False

    def defeat_hint(self) -> str:
        if self.encounter.key == "sableye" and not self.heavy_slam_used:
            return SABLEYE_DEFEAT_HINT
        return ""

    @staticmethod
    def stage_multiplier(stage: int) -> float:
        stage = max(-6, min(6, stage))
        return (2 + stage) / 2 if stage >= 0 else 2 / (2 - stage)

    def peek_foe_move(self) -> MoveSpec:
        return self.encounter.foe_moves[self.foe_turn % len(self.encounter.foe_moves)]

    def choose_foe_move(self) -> MoveSpec:
        move = self.peek_foe_move()
        self.foe_turn += 1
        return move

    def strategy_hint(self) -> str:
        return (f"下招：{self.peek_foe_move().name}  "
                f"我攻+{self.player_attack}/特攻+{self.player_sp_attack} "
                f"敌攻+{self.foe_attack}/防{self.foe_defense}")

    def attack_damage(self, move: MoveSpec, *, player: bool) -> int:
        critical = self.rng.randint(1, 8 if move.high_crit else 24) == 1
        attack = (self.player_sp_attack if move.category == "特殊" else self.player_attack) if player else self.foe_attack
        if move.secondary == "foul_play":
            attack = self.player_attack
        defense = (self.foe_sp_defense if move.category == "特殊" else self.foe_defense) if player else 0
        if critical:
            attack, defense = max(0, attack), min(0, defense)
        damage = self.roll_damage(move) * self.stage_multiplier(attack) / self.stage_multiplier(defense)
        if move.secondary == "acrobatics":
            damage *= 2  # Neither side carries a held item in this game.
        if critical:
            damage *= 1.5
            self.last_message += "击中要害！"
        return max(1, round(damage))

    def roll_damage(self, move: MoveSpec) -> int:
        """Roll uniformly within the authored range, then apply sensor scaling."""
        maximum = move.damage if move.damage_max is None else move.damage_max
        base_damage = self.rng.randint(move.damage, maximum)
        return max(1, round(base_damage * move.damage_scale)) if base_damage else 0

    def use_player_move(self, move: MoveSpec) -> int:
        self.last_message = ""
        self.last_effect = move.effect
        if self.flinched:
            self.last_effect = ""
            self.flinched = False
            self.protect_chain = 0
            self.last_message = "畏缩了，无法行动！"
            return 0
        if move.effect == "protect":
            success = self.rng.randint(1, 3 ** min(self.protect_chain, 6)) == 1
            self.protect_chain += 1
            self.protected = success
            if not success:
                self.last_effect = ""
            self.last_message = "摆出守住架势！" if success else "连续守住失败了！"
            return 0
        self.protect_chain = 0
        if move == self.encounter.hidden_move:
            self.heavy_slam_used = True
        if move.effect == "growth":
            before = self.player_attack
            self.player_attack = min(6, self.player_attack + 1)
            self.player_sp_attack = min(6, self.player_sp_attack + 1)
            self.last_message = "攻击、特攻提升！" if before < 6 else "能力已经到顶了！"
            return 0
        if move.heal_percent:
            amount = round(self.player_max_hp * move.heal_percent / 100)
            before = self.player_hp
            self.player_hp = min(self.player_max_hp, self.player_hp + amount)
            self.last_message = f"回复了{self.player_hp - before}点体力！"
            return self.player_hp - before
        before = self.foe_hp
        self.foe_hp = max(0, self.foe_hp - self.attack_damage(move, player=True))
        self.last_message += f"造成{before - self.foe_hp}点伤害！"
        return before - self.foe_hp

    def use_foe_move(self, move: MoveSpec) -> int:
        self.last_message = ""
        self.last_effect = move.effect
        self.flinched = False
        if self.protected:
            self.last_effect = "protect"
            self.protected = False
            self.last_message = "坚果哑铃守住了攻击！"
            return 0
        if self.rng.randint(1, 100) > move.accuracy:
            self.last_effect = ""
            self.last_message = "攻击没有命中！"
            return 0
        before = self.player_hp
        self.player_hp = max(0, self.player_hp - self.attack_damage(move, player=False))
        if move.secondary == "defenses_down":
            self.foe_defense = max(-6, self.foe_defense - 1)
            self.foe_sp_defense = max(-6, self.foe_sp_defense - 1)
            self.last_message += "对手双防下降！"
        elif move.secondary == "attack_up" and self.rng.randint(1, 100) <= 20:
            self.foe_attack = min(6, self.foe_attack + 1)
            self.last_message += "对手攻击提升！"
        elif (move.secondary == "flinch" and self.encounter.foe_moves_first
              and self.player_hp > 0 and self.rng.randint(1, 100) <= 30):
            self.flinched = True
            self.last_message += "坚果哑铃畏缩了！"
        self.last_message += f"受到{before - self.player_hp}点伤害！"
        return before - self.player_hp


def draw_status_effect(pg, surface, effect, center, ticks):
    """Small pixel-aligned effects shared by the demo and story renderer."""
    x, y = center
    if effect == "protect":
        radius = 42 + int(4 * math.sin(ticks / 100))
        pg.draw.ellipse(surface, (136, 224, 248), (x - radius, y - 52, radius * 2, 96), 4)
        pg.draw.ellipse(surface, (232, 248, 255), (x - radius + 6, y - 46, radius * 2 - 12, 84), 2)
    elif effect == "growth":
        for dx in (-30, 0, 30):
            top = y + 24 - (ticks // 18 + abs(dx)) % 64
            pg.draw.line(surface, (176, 248, 128), (x + dx, top + 16), (x + dx, top), 4)
            pg.draw.lines(surface, (232, 255, 176), False,
                          [(x + dx - 6, top + 6), (x + dx, top), (x + dx + 6, top + 6)], 4)


def draw_strategy_panel(pg, surface, font, rules):
    pg.draw.rect(surface, (248, 248, 224), (202, 6, 272, 38))
    pg.draw.rect(surface, (88, 104, 72), (202, 6, 272, 38), 2)
    lines = (
        f"下招：{rules.peek_foe_move().name}",
        f"我攻+{rules.player_attack} 特攻+{rules.player_sp_attack} "
        f"敌攻+{rules.foe_attack} 防{rules.foe_defense}",
    )
    for index, line in enumerate(lines):
        surface.blit(font.render(line, False, INFO_COLOR), (208, 8 + index * 16))


class BattleEncounterDemo:
    PHASE_INTRO = "intro"
    PHASE_MENU = "menu"
    PHASE_PLAYER_MESSAGE = "player_message"
    PHASE_PLAYER_ACTION = "player_action"
    PHASE_FOE_MESSAGE = "foe_message"
    PHASE_FOE_ACTION = "foe_action"
    PHASE_FAINT_MESSAGE = "faint_message"
    PHASE_FAINTING = "fainting"
    PHASE_RESULT = "result"

    def __init__(
        self,
        pg,
        *,
        encounter_key: str = "zubat",
        seed: int | None = None,
        audio: bool = True,
    ) -> None:
        self.pg = pg
        self.seed = seed
        self.rng = random.Random(seed)
        self.encounter = ENCOUNTERS[encounter_key]
        self.canvas = pg.Surface(LOGICAL_SIZE)
        self.window = pg.display.set_mode(
            (LOGICAL_SIZE[0] * DEFAULT_WINDOW_SCALE, LOGICAL_SIZE[1] * DEFAULT_WINDOW_SCALE),
            pg.RESIZABLE,
        )
        self.clock = pg.time.Clock()
        # This game consumes keys, never text. Disable Windows IME composition.
        pg.key.stop_text_input()
        self.running = True
        self.audio_enabled = audio

        self.font = self._font(18)
        self.small_font = self._font(14)
        self.assets = self._load_assets()
        self.effects = self._load_effects()
        self.sounds = self._load_sounds() if audio else {}
        self.serial_events = queue.Queue()
        self.light_raw = 0
        self.temperature_raw = None
        self.serial = STCSerialBridge(None, self._queue_serial_event)

        self.hp_tween: dict | None = None
        self.reset(encounter_key)

    def _queue_serial_event(self, kind: str, value: int) -> None:
        self.serial_events.put((kind, value))

    def set_serial_port(self, port: str | None) -> None:
        self.serial.close()
        self.serial = STCSerialBridge(port, self._queue_serial_event)
        self.serial.start()

    def _poll_serial(self) -> None:
        while True:
            try:
                kind, value = self.serial_events.get_nowait()
            except queue.Empty:
                return
            if kind == "light":
                self.light_raw = value
            elif kind == "temperature":
                self.temperature_raw = value
            elif kind == "command":
                self.handle_serial_command(value)

    def _current_player_moves(self) -> tuple[MoveSpec, ...]:
        return tuple(light_adjusted_move(move, self.light_raw) for move in self.encounter.player_moves)

    def _font(self, size: int):
        candidates = (
            ROOT / "assets" / "resource" / "fonts" / "zpix.ttf",
            Path("C:/Windows/Fonts/msyh.ttf"),
            Path("C:/Windows/Fonts/simhei.ttf"),
        )
        for path in candidates:
            if path.is_file():
                return self.pg.font.Font(str(path), size)
        return self.pg.font.Font(None, size)

    def _load_image(self, path: Path, *, alpha: bool = True):
        if not path.is_file():
            raise FileNotFoundError(f"缺少战斗素材：{path}")
        image = self.pg.image.load(str(path))
        return image.convert_alpha() if alpha else image.convert()

    def _load_assets(self) -> dict[str, object]:
        files = {
            "player": BATTLE_ASSETS / "pokemon" / "back" / "ferrothorn.png",
            "foe_box": UI_ASSETS / "databox_foe_2x.png",
            "player_box": UI_ASSETS / "databox_player_2x.png",
            "hp_green": UI_ASSETS / "hp_fill_green_2x.png",
            "hp_yellow": UI_ASSETS / "hp_fill_yellow_2x.png",
            "hp_red": UI_ASSETS / "hp_fill_red_2x.png",
            "message": UI_ASSETS / "panel_message_2x.png",
            "move_list": UI_ASSETS / "panel_move_list_2x.png",
            "move_info": UI_ASSETS / "panel_move_info_2x.png",
            "cursor": UI_ASSETS / "cursor_command_2x.png",
            "continue": UI_ASSETS / "cursor_continue_2x.png",
        }
        for key, encounter in ENCOUNTERS.items():
            background = encounter.background
            files[f"background_{key}"] = BATTLE_ASSETS / "backgrounds" / f"{background}_bg.png"
            files[f"player_base_{key}"] = BATTLE_ASSETS / "backgrounds" / f"{background}_base0.png"
            files[f"foe_base_{key}"] = BATTLE_ASSETS / "backgrounds" / f"{background}_base1.png"
            files[f"foe_{key}"] = BATTLE_ASSETS / "pokemon" / "front" / f"{key}.png"
        loaded_by_path = {}
        assets = {}
        for name, path in files.items():
            if path not in loaded_by_path:
                loaded_by_path[path] = self._load_image(path)
            assets[name] = loaded_by_path[path]
        return assets

    def _load_effect_sheet(self, filename: str) -> list:
        sheet = self._load_image(BATTLE_ASSETS / "effects" / filename)
        cell = 192
        frames = []
        for x in range(0, sheet.get_width() - cell + 1, cell):
            frame = sheet.subsurface((x, 0, cell, cell)).copy()
            if frame.get_bounding_rect(min_alpha=1).width:
                frames.append(frame)
        return frames

    def _load_effects(self) -> dict[str, list]:
        return {
            "solar": self._load_effect_sheet("solar_beam_core.png"),
            "synthesis": self._load_effect_sheet("synthesis_heal.png"),
            "attack": self._load_effect_sheet("attack_basic.png"),
            "tackle": self._load_effect_sheet("tackle.png"),
            "rock": self._load_effect_sheet("rock_debris.png"),
            "heavy": self._load_effect_sheet("heavy_slam.png"),
        }

    def _load_sounds(self) -> dict[str, object]:
        if not self.pg.mixer.get_init():
            return {}
        files = {
            "cursor": AUDIO_ASSETS / "se" / "ui_cursor.ogg",
            "confirm": AUDIO_ASSETS / "se" / "ui_confirm.ogg",
            "blocked": AUDIO_ASSETS / "se" / "ui_blocked.ogg",
            "damage": AUDIO_ASSETS / "se" / "damage_normal.ogg",
            "faint": AUDIO_ASSETS / "se" / "pokemon_faint.ogg",
            "solar": AUDIO_ASSETS / "se" / "moves" / "impact.ogg",
            "synthesis": AUDIO_ASSETS / "se" / "moves" / "synthesis_heal.ogg",
            "zubat_cry": AUDIO_ASSETS / "cries" / "zubat.ogg",
            "aron_cry": AUDIO_ASSETS / "cries" / "aron.ogg",
            "sableye_cry": AUDIO_ASSETS / "cries" / "sableye.ogg",
        }
        sounds = {}
        for name, path in files.items():
            try:
                sounds[name] = self.pg.mixer.Sound(str(path))
            except (FileNotFoundError, self.pg.error):
                pass
        return sounds

    def _play_sound(self, name: str) -> None:
        sound = self.sounds.get(name)
        if sound:
            sound.play()

    def _start_music(self, relative_path: str) -> None:
        if not self.audio_enabled or not self.pg.mixer.get_init():
            return
        try:
            self.pg.mixer.music.load(str(AUDIO_ASSETS / relative_path))
            self.pg.mixer.music.set_volume(0.55)
            self.pg.mixer.music.play(-1)
        except (FileNotFoundError, self.pg.error):
            pass

    def reset(self, encounter_key: str | None = None) -> None:
        if encounter_key is not None:
            self.encounter = ENCOUNTERS[encounter_key]
        if self.pg.mixer.get_init():
            self.pg.mixer.stop()
        self.rng = random.Random(self.seed)
        self.pg.display.set_caption(
            f"坚果矿洞大冒险：七日与千年的心愿 - "
            f"坚果哑铃 VS {self.encounter.enemy_name} [{self.encounter.number}/3]"
        )
        self.rules = EncounterBattleRules(self.encounter, self.rng)
        self.display_player_hp = float(self.rules.player_hp)
        self.display_foe_hp = float(self.rules.foe_hp)
        self.hp_tween = None
        self.cursor = 0
        self.menu_hint: tuple[str, str] | None = None
        self.menu_hint_until = 0
        self.selected_move = None
        self.foe_move = None
        self.effect_name = None
        self.fainted_side = None
        self.opening_messages = (
            f"{self.encounter.enemy_name}想要对战！",
            *self.encounter.opening_notes,
        )
        self.opening_index = 0
        self._set_phase(self.PHASE_INTRO, self.opening_messages[0])
        self._start_music("bgm/1-09. Battle! (Wild Pokémon).flac")
        self._play_sound(f"{self.encounter.key}_cry")

    def switch_encounter(self, encounter_key: str) -> None:
        if encounter_key == self.encounter.key:
            self.reset()
        else:
            self.reset(encounter_key)

    def _advance_intro(self) -> None:
        self.opening_index += 1
        if self.opening_index < len(self.opening_messages):
            self._set_phase(self.PHASE_INTRO, self.opening_messages[self.opening_index])
        elif self.encounter.foe_moves_first:
            self._choose_foe_move()
        else:
            self._set_phase(self.PHASE_MENU)

    def _set_phase(self, phase: str, message: str = "") -> None:
        self.phase = phase
        self.phase_started = self.pg.time.get_ticks()
        self.message = message
        self.reveal_started = self.phase_started
        self.reveal_complete = not bool(message)

    def _elapsed(self) -> int:
        return self.pg.time.get_ticks() - self.phase_started

    def _message_chars(self) -> int:
        if not self.message:
            return 0
        count = max(1, (self.pg.time.get_ticks() - self.reveal_started) // 34)
        if count >= len(self.message):
            self.reveal_complete = True
            return len(self.message)
        return int(count)

    def _skip_or_confirm(self) -> bool:
        if self.message and not self.reveal_complete:
            self.reveal_started = self.pg.time.get_ticks() - len(self.message) * 34
            self.reveal_complete = True
            return True
        return False

    def _select_player_move(self) -> None:
        self.selected_move = self._current_player_moves()[self.cursor]
        self._play_sound("confirm")
        self._set_phase(self.PHASE_PLAYER_MESSAGE, f"坚果哑铃使出了{self.selected_move.name}！")

    def handle_vibration(self) -> bool:
        """Handle STC-B command 0x09; keyboard Z uses the same path for now."""
        if self.phase != self.PHASE_MENU:
            return False
        if self.encounter.hidden_move is not None:
            self.selected_move = self.encounter.hidden_move
            self._play_sound("confirm")
            self._set_phase(self.PHASE_PLAYER_MESSAGE, f"坚果哑铃使出了{self.selected_move.name}！")
            return True
        moves = self._current_player_moves()
        if self.cursor >= len(moves):
            return False
        move = moves[self.cursor]
        if move.trigger != "vibration":
            return False
        self._select_player_move()
        return True

    def handle_serial_command(self, command: int) -> bool:
        """Map STC-B controls onto the same paths used by the keyboard."""
        if command == STC_VIBRATION_COMMAND:
            return self.handle_vibration()
        key = {
            STC_UP_COMMAND: self.pg.K_UP,
            STC_DOWN_COMMAND: self.pg.K_DOWN,
            STC_LEFT_COMMAND: self.pg.K_LEFT,
            STC_RIGHT_COMMAND: self.pg.K_RIGHT,
            STC_CONFIRM_COMMAND: self.pg.K_RETURN,
            STC_RESET_COMMAND: self.pg.K_r,
        }.get(command)
        if key is None:
            return False
        self.handle_key(key)
        return True

    def _move_cursor(self, key: int) -> None:
        pg = self.pg
        count = len(self.encounter.player_moves)
        previous = self.cursor
        if key in (pg.K_LEFT, pg.K_RIGHT):
            row = self.cursor // 2
            row_moves = [index for index in range(count) if index // 2 == row]
            if len(row_moves) > 1:
                position = row_moves.index(self.cursor)
                self.cursor = row_moves[(position + 1) % len(row_moves)]
        elif key == pg.K_UP and self.cursor >= 2:
            self.cursor %= 2
        elif key == pg.K_DOWN and self.cursor < 2 and count > 2:
            self.cursor = min(self.cursor + 2, count - 1)
        if self.cursor != previous:
            self.menu_hint = None
            self._play_sound("cursor")

    def _begin_player_action(self) -> None:
        assert self.selected_move is not None
        action_message = self.message
        old_player_hp = self.rules.player_hp
        old_foe_hp = self.rules.foe_hp
        self.rules.use_player_move(self.selected_move)
        action_message = self.rules.last_message or action_message
        self.effect_name = self.rules.last_effect
        self.effect_started = self.pg.time.get_ticks()
        self._play_sound(self.effect_name)
        if self.selected_move.heal_percent or self.selected_move.effect in ("growth", "protect"):
            self._start_hp_tween("player", old_player_hp, self.rules.player_hp)
        else:
            self._start_hp_tween("foe", old_foe_hp, self.rules.foe_hp)
        self._set_phase(self.PHASE_PLAYER_ACTION, action_message)
        self.reveal_started -= len(action_message) * 34
        self.reveal_complete = True

    def _choose_foe_move(self) -> None:
        self.foe_move = self.rules.choose_foe_move()
        self._set_phase(
            self.PHASE_FOE_MESSAGE,
            f"{self.encounter.enemy_name}使出了{self.foe_move.name}！",
        )

    def _begin_foe_action(self) -> None:
        assert self.foe_move is not None
        action_message = self.message
        old_hp = self.rules.player_hp
        self.rules.use_foe_move(self.foe_move)
        action_message = self.rules.last_message or action_message
        self.effect_name = self.rules.last_effect
        self.effect_started = self.pg.time.get_ticks()
        self._play_sound("damage")
        self._start_hp_tween("player", old_hp, self.rules.player_hp)
        self._set_phase(self.PHASE_FOE_ACTION, action_message)
        self.reveal_started -= len(action_message) * 34
        self.reveal_complete = True

    def _start_hp_tween(self, side: str, start: int, end: int) -> None:
        self.hp_tween = {
            "side": side,
            "start": float(start),
            "end": float(end),
            "started": self.pg.time.get_ticks(),
            "duration": 620,
        }

    def _finish_hp_tween(self) -> None:
        if not self.hp_tween:
            return
        side = self.hp_tween["side"]
        value = self.hp_tween["end"]
        if side == "player":
            self.display_player_hp = value
        else:
            self.display_foe_hp = value
        self.hp_tween = None

    def _start_faint(self, side: str) -> None:
        self.fainted_side = side
        name = self.encounter.enemy_name if side == "foe" else "坚果哑铃"
        self._set_phase(self.PHASE_FAINT_MESSAGE, f"{name}倒下了！")

    def _begin_faint_animation(self) -> None:
        faint_message = self.message
        self._play_sound("faint")
        self._set_phase(self.PHASE_FAINTING, faint_message)
        self.reveal_started -= len(faint_message) * 34
        self.reveal_complete = True

    def _finish_battle(self) -> None:
        if self.pg.mixer.get_init():
            self.pg.mixer.music.stop()
        winner = (
            "坚果哑铃赢得了战斗！"
            if self.fainted_side == "foe"
            else f"{self.encounter.enemy_name}赢得了战斗！"
        )
        hint = self.rules.defeat_hint() if self.fainted_side == "player" else ""
        self._set_phase(self.PHASE_RESULT, hint or (winner + "  Enter重新开始"))
        if self.fainted_side == "foe":
            self._start_music("bgm/battle_victory.ogg")

    def handle_key(self, key: int) -> None:
        pg = self.pg
        if key == pg.K_ESCAPE:
            self.running = False
            return
        encounter_keys = {
            pg.K_1: "zubat",
            pg.K_KP1: "zubat",
            pg.K_2: "aron",
            pg.K_KP2: "aron",
            pg.K_3: "sableye",
            pg.K_KP3: "sableye",
        }
        if key in encounter_keys:
            self.switch_encounter(encounter_keys[key])
            return
        if key == pg.K_z:
            self.handle_serial_command(STC_VIBRATION_COMMAND)
            return
        if key == pg.K_r:
            self.reset()
            return
        if self.phase == self.PHASE_MENU:
            if key in (pg.K_LEFT, pg.K_RIGHT, pg.K_UP, pg.K_DOWN):
                self._move_cursor(key)
            elif key in (pg.K_RETURN, pg.K_SPACE):
                move = self._current_player_moves()[self.cursor]
                if move.trigger == "vibration":
                    self.menu_hint = ("需要敲击小板", "或按Z触发")
                    self.menu_hint_until = pg.time.get_ticks() + 1500
                    self._play_sound("blocked")
                else:
                    self._select_player_move()
            return
        if key not in (pg.K_RETURN, pg.K_SPACE):
            return
        if self.phase in (self.PHASE_PLAYER_ACTION, self.PHASE_FOE_ACTION):
            self._finish_hp_tween()
            self.phase_started = self.pg.time.get_ticks() - 1800
            self.update()
            return
        if self._skip_or_confirm():
            return
        if self.phase == self.PHASE_INTRO:
            self._play_sound("confirm")
            self._advance_intro()
        elif self.phase == self.PHASE_FAINT_MESSAGE:
            self._begin_faint_animation()
        elif self.phase == self.PHASE_RESULT:
            self.reset()
        elif self.phase == self.PHASE_PLAYER_MESSAGE:
            self._begin_player_action()
        elif self.phase == self.PHASE_FOE_MESSAGE:
            self._begin_foe_action()

    def update(self) -> None:
        self._poll_serial()
        self._update_hp_tween()
        elapsed = self._elapsed()
        if (
            self.phase == self.PHASE_INTRO
            and self.opening_index > 0
            and self.reveal_complete
            and elapsed >= len(self.message) * 34 + 1400
        ):
            self._advance_intro()
        elif self.phase == self.PHASE_PLAYER_MESSAGE and self.reveal_complete and elapsed >= 920:
            self._begin_player_action()
        elif self.phase == self.PHASE_PLAYER_ACTION and elapsed >= 1800 and not self.hp_tween:
            if self.rules.foe_hp <= 0:
                self._start_faint("foe")
            else:
                self._choose_foe_move()
        elif self.phase == self.PHASE_FOE_MESSAGE and self.reveal_complete and elapsed >= 920:
            self._begin_foe_action()
        elif self.phase == self.PHASE_FOE_ACTION and elapsed >= 1800 and not self.hp_tween:
            if self.rules.player_hp <= 0:
                self._start_faint("player")
            else:
                self._set_phase(self.PHASE_MENU)
        elif self.phase == self.PHASE_FAINT_MESSAGE and self.reveal_complete and elapsed >= 1250:
            self._begin_faint_animation()
        elif self.phase == self.PHASE_FAINTING and elapsed >= 980:
            self._finish_battle()

    def _update_hp_tween(self) -> None:
        if not self.hp_tween:
            return
        tween = self.hp_tween
        progress = min(1.0, (self.pg.time.get_ticks() - tween["started"]) / tween["duration"])
        value = tween["start"] + (tween["end"] - tween["start"]) * progress
        if tween["side"] == "player":
            self.display_player_hp = value
        else:
            self.display_foe_hp = value
        if progress >= 1.0:
            self._finish_hp_tween()

    def run(self) -> None:
        while self.running:
            for event in self.pg.event.get():
                if event.type == self.pg.QUIT:
                    self.running = False
                elif event.type == self.pg.KEYDOWN:
                    self.handle_key(event.key)
                elif event.type == self.pg.WINDOWFOCUSGAINED:
                    self.pg.key.stop_text_input()
                elif event.type == self.pg.VIDEORESIZE:
                    size = (max(LOGICAL_SIZE[0], event.w), max(LOGICAL_SIZE[1], event.h))
                    self.window = self.pg.display.set_mode(size, self.pg.RESIZABLE)
                    self.pg.key.stop_text_input()
            self.update()
            self.draw()
            self._present()
            self.clock.tick(FPS)

    def _present(self) -> None:
        window_w, window_h = self.window.get_size()
        scale = max(1, min(window_w // LOGICAL_SIZE[0], window_h // LOGICAL_SIZE[1]))
        size = (LOGICAL_SIZE[0] * scale, LOGICAL_SIZE[1] * scale)
        self.window.fill((16, 16, 16))
        scaled = self.pg.transform.scale(self.canvas, size)
        self.window.blit(scaled, ((window_w - size[0]) // 2, (window_h - size[1]) // 2))
        self.pg.display.flip()

    def draw(self) -> None:
        self._draw_arena()
        self._draw_databoxes()
        self._draw_menu()

    def _draw_arena(self) -> None:
        pg = self.pg
        key = self.encounter.key
        background = self.assets[f"background_{key}"]
        # These battle layers are already 2x pixels. Crop instead of resampling.
        self.canvas.blit(background, (0, 0), (16, 0, 480, 228))
        self.canvas.blit(self.assets[f"player_base_{key}"], (-16, 166))
        self.canvas.blit(self.assets[f"foe_base_{key}"], (240, 44))

        elapsed = self._elapsed()
        intro = min(1.0, elapsed / 560) if self.phase == self.PHASE_INTRO else 1.0
        foe_bob = round(2 * math.sin(pg.time.get_ticks() / 210))
        player_x = round(-120 + 168 * intro)
        foe_x = round(440 - 148 * intro)
        player_y = 62
        foe_y = 8 + foe_bob

        if self.phase == self.PHASE_FOE_ACTION:
            player_x += 6 if (elapsed // 70) % 2 == 0 else -6
        if self.phase == self.PHASE_PLAYER_ACTION and self.selected_move and self.selected_move.damage:
            foe_x += 4 if (elapsed // 70) % 2 == 0 else -4

        player_visible = not (self.fainted_side == "player" and self.phase == self.PHASE_RESULT)
        foe_visible = not (self.fainted_side == "foe" and self.phase == self.PHASE_RESULT)
        if self.phase == self.PHASE_FAINTING:
            drop = min(96, round(elapsed * 0.1))
            if self.fainted_side == "player":
                player_y += drop
            else:
                foe_y += drop

        if player_visible:
            self.canvas.blit(self.assets["player"], (player_x, player_y))
        if foe_visible:
            self.canvas.blit(self.assets[f"foe_{key}"], (foe_x, foe_y))
        self._draw_effects()

    def _draw_effects(self) -> None:
        if self.phase not in (self.PHASE_PLAYER_ACTION, self.PHASE_FOE_ACTION) or not self.effect_name:
            return
        if self.effect_name in ("growth", "protect"):
            draw_status_effect(self.pg, self.canvas, self.effect_name, (126, 142),
                               self.pg.time.get_ticks() - self.effect_started)
            return
        frames = self.effects.get(self.effect_name, [])
        if not frames:
            return
        elapsed = self.pg.time.get_ticks() - self.effect_started
        frame = frames[min(len(frames) - 1, elapsed // 110)]
        if self.phase == self.PHASE_FOE_ACTION or (self.selected_move and self.selected_move.heal_percent):
            target = frame.get_rect(center=(126, 142))
        else:
            target = frame.get_rect(center=(372, 100))
        self.canvas.blit(frame, target)

    def _draw_databoxes(self) -> None:
        self.canvas.blit(self.assets["foe_box"], FOE_BOX_RECT[:2])
        self.canvas.blit(self.assets["player_box"], PLAYER_BOX_RECT[:2])
        self.canvas.blit(self.font.render(self.encounter.enemy_name, False, TEXT_COLOR), (18, 18))
        self.canvas.blit(self.font.render("坚果哑铃", False, TEXT_COLOR), (292, 156))
        self._draw_hp_bar("foe", self.display_foe_hp, self.rules.foe_max_hp)
        self._draw_hp_bar("player", self.display_player_hp, self.rules.player_max_hp)
        hp_text = f"{round(self.display_player_hp)}/{self.rules.player_max_hp}"
        rendered = self.small_font.render(hp_text, False, TEXT_COLOR)
        self.canvas.blit(rendered, (466 - rendered.get_width(), 194))

    def _draw_hp_bar(self, side: str, hp: float, maximum: int) -> None:
        ratio = max(0.0, min(1.0, hp / maximum))
        asset = "hp_green" if ratio > 0.5 else ("hp_yellow" if ratio > 0.2 else "hp_red")
        width = max(0, min(96, round(96 * ratio / 2) * 2))
        if not width:
            return
        x, y = (86, 44) if side == "foe" else (366, 184)
        self.canvas.blit(self.assets[asset], (x, y), (0, 0, width, 6))

    def _draw_menu(self) -> None:
        if self.phase == self.PHASE_MENU:
            self._draw_move_menu()
        else:
            self._draw_message_panel()

    def _draw_move_menu(self) -> None:
        self.canvas.blit(self.assets["move_list"], MOVE_LIST_POS)
        self.canvas.blit(self.assets["move_info"], MOVE_INFO_POS)
        positions = ((28, 234), (174, 234), (28, 274), (174, 274))
        player_moves = self._current_player_moves()
        for index, position in enumerate(positions):
            if index < len(player_moves):
                text = player_moves[index].name
                font = self.font
                color = TEXT_COLOR
            else:
                text = "—"
                font = self.small_font
                color = (128, 128, 128)
            self.canvas.blit(font.render(text, False, color), position)
        cursor_x = 8 + (self.cursor % 2) * 146
        cursor_y = 232 + (self.cursor // 2) * 40
        self.canvas.blit(self.assets["cursor"], (cursor_x, cursor_y))

        move = player_moves[self.cursor]
        if self.menu_hint and self.pg.time.get_ticks() < self.menu_hint_until:
            info_lines = self.menu_hint
        else:
            self.menu_hint = None
            info_lines = move.info_lines or (f"属性/{move.category}", move.value_label)
        self.canvas.blit(self.small_font.render(info_lines[0], False, INFO_COLOR), (338, 236))
        self.canvas.blit(self.small_font.render(info_lines[1], False, INFO_COLOR), (338, 272))
        draw_strategy_panel(self.pg, self.canvas, self.small_font, self.rules)

    def _draw_message_panel(self) -> None:
        self.canvas.blit(self.assets["message"], MESSAGE_POS)
        visible = self.message[: self._message_chars()]
        self._draw_wrapped_text(visible, (18, 244), 444)
        confirm_phases = (self.PHASE_INTRO, self.PHASE_FAINT_MESSAGE, self.PHASE_RESULT)
        if self.phase in confirm_phases and self.reveal_complete:
            cursor = self.assets["continue"]
            bob = 2 if (self.pg.time.get_ticks() // 260) % 2 else 0
            self.canvas.blit(cursor, (444, 288 + bob))

    def _draw_wrapped_text(self, text: str, position: tuple[int, int], max_width: int) -> None:
        x, y = position
        lines = []
        line = ""
        for char in text:
            candidate = line + char
            if line and self.font.size(candidate)[0] > max_width:
                lines.append(line)
                line = char
            else:
                line = candidate
        if line:
            lines.append(line)
        for index, line_text in enumerate(lines[:2]):
            self.canvas.blit(self.font.render(line_text, False, MESSAGE_COLOR), (x, y + index * 30))

    def save_screenshot(self, path: Path, phase: str) -> None:
        if phase == "menu":
            self.phase = self.PHASE_MENU
            self.phase_started = self.pg.time.get_ticks() - 1000
            self.message = ""
            self.reveal_complete = True
        elif phase == "intro":
            self.phase_started = self.pg.time.get_ticks() - 1000
            self.reveal_started = self.phase_started
            self.reveal_complete = True
        else:
            raise ValueError(f"不支持的截图阶段：{phase}")
        self.draw()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.pg.image.save(self.canvas, str(path))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="《坚果矿洞大冒险：七日与千年的心愿》战斗测试"
    )
    parser.add_argument(
        "--encounter",
        choices=tuple(ENCOUNTERS),
        default="zubat",
        help="启动时显示的战斗",
    )
    parser.add_argument("--seed", type=int, default=None, help="固定敌方选招随机种子")
    parser.add_argument("--mute", action="store_true", help="关闭 BGM 和音效")
    parser.add_argument("--port", help="STC-B 串口号，例如 COM3")
    parser.add_argument("--screenshot", type=Path, help="无窗口保存 480x320 测试截图")
    parser.add_argument("--phase", choices=("intro", "menu"), default="menu", help="截图阶段")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.screenshot:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    try:
        import pygame
    except ImportError:
        print("缺少 pygame，请先运行：pip install -r requirements.txt", file=sys.stderr)
        return 1

    pygame.init()
    if not args.mute:
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
        except pygame.error:
            pass
    try:
        demo = BattleEncounterDemo(
            pygame,
            encounter_key=args.encounter,
            seed=args.seed,
            audio=not args.mute,
        )
        demo.set_serial_port(args.port)
        if args.screenshot:
            demo.save_screenshot(args.screenshot.resolve(), args.phase)
            print(args.screenshot.resolve())
        else:
            demo.run()
    finally:
        if "demo" in locals():
            demo.serial.close()
        pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
