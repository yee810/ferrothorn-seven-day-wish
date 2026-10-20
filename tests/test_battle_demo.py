import random
import unittest

import _bootstrap  # noqa: F401

from battle_demo import (
    ENCOUNTERS,
    FOE_BOX_RECT,
    MESSAGE_POS,
    MOVE_INFO_POS,
    MOVE_LIST_POS,
    PLAYER_BOX_RECT,
    STC_CONFIRM_COMMAND,
    STC_CONTROL_COMMANDS,
    STC_RESET_COMMAND,
    STC_RIGHT_COMMAND,
    STC_VIBRATION_COMMAND,
    STCSerialBridge,
    EncounterBattleRules,
    light_adjusted_move,
    light_solar_power,
    light_synthesis_percent,
)


class EncounterBattleRulesTests(unittest.TestCase):
    def test_encounter_specs_match_source_files(self):
        expected = {
            "zubat": (100, (24, 28), 30, ((19, 23), (30, 35), (12, 14)), "威力：70"),
            "aron": (204, (33, 40), 30, ((16, 20), (20, 24), (25, 30)), "威力：70"),
            "sableye": (280, (16, 19), 20, ((24, 28), (44, 50), (24, 28)), "威力：40"),
        }
        for key, values in expected.items():
            encounter = ENCOUNTERS[key]
            foe_hp, solar_range, heal_percent, foe_ranges, power_label = values
            self.assertEqual(encounter.enemy_max_hp, foe_hp)
            solar = next(m for m in encounter.player_moves if m.effect == "solar")
            self.assertEqual((solar.damage, solar.damage_max), solar_range)
            self.assertEqual(solar.value_label, power_label)
            self.assertEqual(next(m for m in encounter.player_moves if m.effect == "synthesis").heal_percent, heal_percent)
            self.assertEqual(
                tuple((move.damage, move.damage_max) for move in encounter.foe_moves),
                foe_ranges,
            )

    def test_each_encounter_starts_with_correct_hp(self):
        for key, encounter in ENCOUNTERS.items():
            battle = EncounterBattleRules(key)
            self.assertEqual((battle.player_hp, battle.foe_hp), (149, encounter.enemy_max_hp))

    def test_damage_rolls_stay_inside_each_authored_range(self):
        for key, encounter in ENCOUNTERS.items():
            battle = EncounterBattleRules(key, random.Random(27))
            for move in (next(m for m in encounter.player_moves if m.effect == "solar"), *encounter.foe_moves):
                rolls = [battle.roll_damage(move) for _ in range(100)]
                maximum = move.damage if move.damage_max is None else move.damage_max
                self.assertGreaterEqual(min(rolls), move.damage)
                self.assertLessEqual(max(rolls), maximum)
                self.assertGreater(len(set(rolls)), 1)

    def test_synthesis_heals_the_configured_percentage(self):
        for key, encounter in ENCOUNTERS.items():
            battle = EncounterBattleRules(key)
            battle.player_hp = 70
            move = next(m for m in encounter.player_moves if m.effect == "synthesis")
            expected_heal = min(149 - 70, round(149 * move.heal_percent / 100))
            self.assertEqual(battle.use_player_move(move), expected_heal)

    def test_seeded_foe_selection_is_repeatable(self):
        for encounter in ENCOUNTERS.values():
            first = random.Random(17).choice(encounter.foe_moves)
            second = random.Random(17).choice(encounter.foe_moves)
            self.assertEqual(first, second)

    def test_seeded_damage_rolls_are_repeatable(self):
        for key, encounter in ENCOUNTERS.items():
            first = EncounterBattleRules(key, random.Random(17))
            second = EncounterBattleRules(key, random.Random(17))
            move = encounter.player_moves[0]
            self.assertEqual(
                [first.roll_damage(move) for _ in range(20)],
                [second.roll_damage(move) for _ in range(20)],
            )

    def test_sableye_has_heavy_slam_vibration_move(self):
        move = ENCOUNTERS["sableye"].hidden_move
        self.assertEqual((move.name, move.damage, move.damage_max), ("重磅冲撞", 50, 59))
        self.assertEqual(move.info_lines, ("双方体重相差越大", "威力越高"))
        self.assertEqual(move.trigger, "vibration")
        self.assertEqual(STC_VIBRATION_COMMAND, 0x09)

    def test_sableye_has_both_cave_tutorial_notes(self):
        notes = ENCOUNTERS["sableye"].opening_notes
        self.assertEqual(len(notes), 1)
        self.assertIn("光线较弱", notes[0])
        self.assertNotIn("敲击", "".join(notes))
        self.assertFalse(ENCOUNTERS["aron"].opening_notes)

    def test_zubat_and_aron_move_before_the_player(self):
        self.assertTrue(ENCOUNTERS["zubat"].foe_moves_first)
        self.assertTrue(ENCOUNTERS["aron"].foe_moves_first)
        self.assertFalse(ENCOUNTERS["sableye"].foe_moves_first)

    def test_foe_first_encounter_queues_an_attack_after_the_intro(self):
        from battle_demo import BattleEncounterDemo
        demo = object.__new__(BattleEncounterDemo)
        demo.encounter = ENCOUNTERS["zubat"]
        demo.opening_messages = ("超音蝠想要对战！",)
        demo.opening_index = 0
        queued = []
        demo._choose_foe_move = lambda: queued.append(True)
        demo._set_phase = lambda *_args: self.fail("不应先进入玩家菜单")
        demo._advance_intro()
        self.assertEqual(queued, [True])

    def test_primary_layout_uses_2x_pixel_coordinates(self):
        layouts = (FOE_BOX_RECT, PLAYER_BOX_RECT, MESSAGE_POS, MOVE_LIST_POS, MOVE_INFO_POS)
        self.assertTrue(all(value % 2 == 0 for layout in layouts for value in layout))

    def test_light_mapping_uses_the_requested_endpoints_and_clamp(self):
        self.assertEqual(light_solar_power(0), 70)
        self.assertEqual(light_solar_power(105), 120)
        self.assertEqual(light_solar_power(500), 120)
        self.assertEqual(light_synthesis_percent(0), 30)
        self.assertEqual(light_synthesis_percent(105), 50)
        self.assertEqual(light_synthesis_percent(500), 50)

    def test_light_mapping_changes_inside_the_normal_range(self):
        self.assertGreater(light_solar_power(90), 70)
        self.assertLess(light_solar_power(90), 120)
        self.assertGreater(light_synthesis_percent(90), 30)
        self.assertLess(light_synthesis_percent(90), 50)

    def test_sableye_uses_its_lower_light_ranges(self):
        solar, synthesis = ENCOUNTERS["sableye"].player_moves[2:]
        dark_solar = light_adjusted_move(solar, 0)
        bright_solar = light_adjusted_move(solar, 105)
        dark_synthesis = light_adjusted_move(synthesis, 0)
        bright_synthesis = light_adjusted_move(synthesis, 105)
        self.assertEqual((dark_solar.value_label, bright_solar.value_label), ("威力：40", "威力：80"))
        self.assertEqual((dark_solar.damage_scale, bright_solar.damage_scale), (1.0, 2.0))
        self.assertEqual(
            (dark_synthesis.value_label, bright_synthesis.value_label),
            ("回复量：20%", "回复量：40%"),
        )
        self.assertEqual((dark_synthesis.heal_percent, bright_synthesis.heal_percent), (20, 40))

    def test_sableye_solar_damage_scales_after_the_random_roll(self):
        class HighestRoll:
            @staticmethod
            def randint(_minimum, maximum):
                return maximum

        solar = ENCOUNTERS["sableye"].player_moves[2]
        battle = EncounterBattleRules("sableye", HighestRoll())
        self.assertEqual(battle.roll_damage(light_adjusted_move(solar, 0)), 19)
        self.assertEqual(battle.roll_damage(light_adjusted_move(solar, 105)), 38)

    def test_vibration_is_safe_when_cursor_has_no_move(self):
        # Z/0x09 can arrive asynchronously while switching encounters.
        from battle_demo import BattleEncounterDemo
        demo = object.__new__(BattleEncounterDemo)
        demo.encounter = ENCOUNTERS["zubat"]
        demo.phase = demo.PHASE_MENU
        demo.cursor = 2
        demo.light_raw = 0
        self.assertFalse(demo.handle_vibration())

    def test_serial_bridge_forwards_navigation_confirm_reset_and_vibration(self):
        events = []
        bridge = STCSerialBridge(None, lambda kind, value: events.append((kind, value)))
        for command in STC_CONTROL_COMMANDS:
            bridge._handle_byte(command)
        self.assertEqual(
            set(events),
            {("command", command) for command in STC_CONTROL_COMMANDS},
        )

    def test_stc_navigation_confirm_and_reset_map_to_keyboard_controls(self):
        from battle_demo import BattleEncounterDemo
        demo = object.__new__(BattleEncounterDemo)
        demo.pg = type(
            "FakePygame",
            (),
            {"K_UP": 1, "K_DOWN": 2, "K_LEFT": 3, "K_RIGHT": 4, "K_RETURN": 5, "K_r": 6},
        )
        received = []
        demo.handle_key = received.append
        expected = {
            0x01: demo.pg.K_UP,
            0x02: demo.pg.K_DOWN,
            0x03: demo.pg.K_LEFT,
            STC_RIGHT_COMMAND: demo.pg.K_RIGHT,
            STC_CONFIRM_COMMAND: demo.pg.K_RETURN,
            STC_RESET_COMMAND: demo.pg.K_r,
        }
        for command, key in expected.items():
            self.assertTrue(demo.handle_serial_command(command))
            self.assertEqual(received[-1], key)
        self.assertFalse(demo.handle_serial_command(0x08))


if __name__ == "__main__":
    unittest.main()
