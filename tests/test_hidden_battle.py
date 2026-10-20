import os
import unittest
import _bootstrap  # noqa: F401

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import pygame
from battle_demo import BattleEncounterDemo, ENCOUNTERS, EncounterBattleRules, SABLEYE_DEFEAT_HINT
from test_adventure import Adventure, dismiss_opening


class HiddenBattleTests(unittest.TestCase):
    def test_hint_tracks_actual_use_not_selection(self):
        rules = EncounterBattleRules("sableye")
        self.assertEqual(rules.defeat_hint(), SABLEYE_DEFEAT_HINT)
        rules.flinched = True
        rules.use_player_move(rules.encounter.hidden_move)
        self.assertTrue(rules.defeat_hint())
        rules.use_player_move(rules.encounter.hidden_move)
        self.assertFalse(rules.defeat_hint())
        self.assertEqual([m.name for m in rules.encounter.player_moves],
                         ["生长", "守住", "日光束", "光合作用"])

    def test_demo_hidden_action_and_fast_forward(self):
        pygame.init()
        demo = BattleEncounterDemo(pygame, encounter_key="sableye", audio=False)
        try:
            for cursor in range(4):
                demo.cursor = cursor
                demo._set_phase(demo.PHASE_MENU)
                self.assertTrue(demo.handle_serial_command(0x09))
                self.assertEqual(demo.selected_move, ENCOUNTERS["sableye"].hidden_move)
                self.assertFalse(demo.handle_vibration())
            demo._begin_player_action()
            hp = demo.rules.foe_hp
            demo.handle_key(pygame.K_RETURN)
            self.assertEqual(demo.phase, demo.PHASE_FOE_MESSAGE)
            self.assertEqual(demo.rules.foe_hp, hp)
            self.assertFalse(demo.rules.defeat_hint())
            demo.draw()
        finally:
            demo.serial.close()
            pygame.quit()

    def test_story_hint_waits_for_confirmation_then_restarts(self):
        game = Adventure(None)
        dismiss_opening(game)
        try:
            game.start_event_battle("sableye")
            battle = game.encounter_battle
            battle.update(stage="lost", message="坚果哑铃倒下了！")
            game.battle_lost = True
            restarted = []
            game.restart_map_event_after_defeat = lambda: restarted.append(True)
            game.sync_encounter_message(force=True)
            game.battle_message_reveal = 1000
            game.command(5)
            self.assertEqual(battle["stage"], "defeat_hint")
            self.assertEqual(battle["message"], SABLEYE_DEFEAT_HINT)
            game.draw()
            self.assertFalse(restarted)
            game.command(5)  # Reveal, do not restart yet.
            self.assertFalse(restarted)
            game.command(5)
            self.assertEqual(restarted, [True])
            battle["rules"].use_player_move(battle["spec"].hidden_move)
            battle.update(stage="lost", message="坚果哑铃倒下了！")
            game.sync_encounter_message(force=True)
            game.battle_message_reveal = 1000
            game.command(5)
            self.assertEqual(len(restarted), 2)
        finally:
            game.serial.close()
            pygame.quit()

    def test_story_z_ignores_cursor_and_fast_forward_keeps_damage(self):
        game = Adventure(None)
        dismiss_opening(game)
        try:
            game.start_event_battle("sableye")
            battle = game.encounter_battle
            for cursor in range(4):
                game.move_cursor = cursor
                battle["stage"] = "menu"
                self.assertTrue(game.encounter_battle_vibration())
                self.assertEqual(battle["selected_move"].name, "重磅冲撞")
                self.assertFalse(game.encounter_battle_vibration())
            game.begin_encounter_player_action()
            hp = battle["rules"].foe_hp
            game.command(5)
            self.assertIsNone(game.battle_effect)
            self.assertEqual(game.enemy_hp, hp)
            self.assertEqual(battle["stage"], "foe_announce")
        finally:
            game.serial.close()
            pygame.quit()


if __name__ == "__main__":
    unittest.main()
