"""Secondary-effect boundaries and reproducible keyboard-only balance checks."""
import random
import unittest

import _bootstrap  # noqa: F401
from battle_demo import ENCOUNTERS, GROWTH, PROTECT, EncounterBattleRules, light_adjusted_move
from scripted_battle import GrotleTutorial


class Rolls:
    def __init__(self, *values):
        self.values = iter(values)

    def randint(self, lo, hi):
        value = next(self.values)
        assert lo <= value <= hi, (lo, value, hi)
        return value


def simulate(key, seed, strategy):
    battle = EncounterBattleRules(key, random.Random(seed))
    moves = tuple(light_adjusted_move(m, None) for m in battle.encounter.player_moves)
    solar = next(m for m in moves if m.effect == "solar")
    heal = next(m for m in moves if m.effect == "synthesis")
    if battle.encounter.foe_moves_first:
        battle.use_foe_move(battle.choose_foe_move())
    for turn in range(80):
        if battle.player_hp <= 0:
            break
        move = battle.encounter.hidden_move if key == "sableye" else solar
        if strategy:
            if key == "sableye" and battle.peek_foe_move().name == "移花接木" and battle.foe_hp > 50:
                move = PROTECT
            elif battle.player_hp < (60 if key == "aron" else 35) and battle.foe_hp > 50:
                move = heal
            elif key == "aron" and battle.player_sp_attack < 1:
                move = moves[2]
        battle.use_player_move(move)
        if battle.foe_hp <= 0:
            return True, turn + 1
        battle.use_foe_move(battle.choose_foe_move())
    return False, 80


class StrategyTests(unittest.TestCase):
    def test_growth_caps_and_changes_special_damage(self):
        battle = EncounterBattleRules("aron", Rolls(24, 33))
        battle.use_player_move(GROWTH)
        self.assertEqual(battle.use_player_move(battle.encounter.player_moves[0]), 50)
        for _ in range(10):
            battle.use_player_move(GROWTH)
        self.assertEqual((battle.player_attack, battle.player_sp_attack), (6, 6))

    def test_protect_blocks_damage_and_secondary_then_expires(self):
        battle = EncounterBattleRules("aron", Rolls(1, 2))
        battle.use_player_move(PROTECT)
        self.assertEqual(battle.use_foe_move(battle.encounter.foe_moves[0]), 0)
        self.assertFalse(battle.protected)
        self.assertFalse(battle.flinched)
        battle.use_player_move(PROTECT)
        self.assertFalse(battle.protected)
        battle.use_player_move(GROWTH)
        self.assertEqual(battle.protect_chain, 0)

    def test_flinch_costs_exactly_one_action(self):
        battle = EncounterBattleRules("aron", Rolls(90, 24, 16, 30))
        battle.use_foe_move(battle.encounter.foe_moves[0])
        self.assertTrue(battle.flinched)
        battle.use_player_move(GROWTH)
        self.assertEqual(battle.player_attack, 0)
        battle.use_player_move(GROWTH)
        self.assertEqual(battle.player_attack, 1)

    def test_miss_has_no_secondary_effect(self):
        battle = EncounterBattleRules("aron", Rolls(91))
        self.assertEqual(battle.use_foe_move(battle.encounter.foe_moves[1]), 0)
        self.assertEqual(battle.foe_attack, 0)

    def test_meteor_mash_boost_boundary(self):
        for roll, stage in ((20, 1), (21, 0)):
            battle = EncounterBattleRules("aron", Rolls(90, 24, 20, roll))
            battle.use_foe_move(battle.encounter.foe_moves[1])
            self.assertEqual(battle.foe_attack, stage)

    def test_dragon_ascent_lowers_both_defenses(self):
        battle = EncounterBattleRules("zubat", Rolls(100, 24, 30, 24, 24))
        battle.use_foe_move(battle.encounter.foe_moves[1])
        self.assertEqual((battle.foe_defense, battle.foe_sp_defense), (-1, -1))
        self.assertEqual(battle.use_player_move(battle.encounter.player_moves[0]), 36)

    def test_acrobatics_doubles_without_an_item(self):
        battle = EncounterBattleRules("zubat", Rolls(100, 24, 12))
        self.assertEqual(battle.use_foe_move(battle.encounter.foe_moves[2]), 24)

    def test_high_crit_and_foul_play(self):
        battle = EncounterBattleRules("sableye", Rolls(100, 1, 24))
        self.assertEqual(battle.use_foe_move(battle.encounter.foe_moves[0]), 36)
        battle = EncounterBattleRules("sableye", Rolls(100, 24, 44))
        battle.player_attack = 2
        battle.foe_attack = 6  # Foul Play must use the target's attack instead.
        self.assertEqual(battle.use_foe_move(battle.encounter.foe_moves[1]), 88)

    def test_forecast_matches_selection_and_reset_is_clean(self):
        battle = EncounterBattleRules("aron")
        for _ in range(8):
            forecast = battle.peek_foe_move()
            self.assertEqual(battle.choose_foe_move(), forecast)
        fresh = EncounterBattleRules("aron")
        self.assertEqual(fresh.foe_turn, 0)
        self.assertFalse(fresh.flinched or fresh.protected)
        self.assertEqual(fresh.player_attack, 0)

    def test_tutorial_completes_at_zero_light_across_seeds(self):
        for seed in range(100):
            tutorial = GrotleTutorial(rng=random.Random(seed))
            for _ in range(80):
                if tutorial.outcome:
                    break
                if tutorial.mode == "action":
                    tutorial.complete_action()
                elif tutorial.mode == "moves":
                    move = tutorial.required_move or ("synthesis" if tutorial.player_hp < 45 else "solar_beam")
                    tutorial.choose_move(move, None)
                else:
                    tutorial.confirm()
            self.assertEqual(tutorial.outcome, "won")

    def test_keyboard_strategy_balance(self):
        for key, minimum in (("zubat", 1.0), ("aron", .94), ("sableye", .93)):
            results = [simulate(key, seed, True) for seed in range(1000)]
            rate = sum(won for won, _ in results) / len(results)
            self.assertGreaterEqual(rate, minimum, (key, rate))
            self.assertLess(sum(turns for won, turns in results if won) / sum(won for won, _ in results), 12)
        simple = sum(simulate("sableye", seed, False)[0] for seed in range(1000))
        smart = sum(simulate("sableye", seed, True)[0] for seed in range(1000))
        self.assertGreater(smart - simple, 500)
        simple = sum(simulate("aron", seed, False)[0] for seed in range(1000))
        smart = sum(simulate("aron", seed, True)[0] for seed in range(1000))
        self.assertGreater(smart - simple, 250)


if __name__ == "__main__":
    unittest.main()
