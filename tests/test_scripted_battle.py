import _bootstrap  # noqa: F401

from scripted_battle import GrotleTutorial


class LowestRoll:
    @staticmethod
    def randint(minimum, _maximum):
        return minimum


class HighestRoll:
    @staticmethod
    def randint(_minimum, maximum):
        return maximum


def advance_to_first_move(tutorial):
    tutorial.confirm()
    tutorial.confirm()
    action = tutorial.confirm()
    assert action and action.target == "player"
    tutorial.complete_action()
    tutorial.confirm()
    tutorial.confirm()


def test_tutorial_unlock_order_and_sensor_ranges():
    tutorial = GrotleTutorial(rng=LowestRoll())
    advance_to_first_move(tutorial)
    assert tutorial.stage == "require_solar"
    assert tutorial.player_hp == 125
    assert tutorial.available_moves == ("solar_beam",)

    action = tutorial.choose_move("solar_beam", 0)
    assert action.amount == 34
    tutorial.complete_action()
    assert tutorial.stage == "praise"

    tutorial.confirm()
    tutorial.confirm()
    action = tutorial.confirm()
    assert action.amount == 24
    tutorial.complete_action()
    tutorial.confirm()
    tutorial.confirm()
    assert tutorial.stage == "require_synthesis"

    action = tutorial.choose_move("solar_beam", 105)
    assert action is None
    assert "光合作用" in tutorial.message
    action = tutorial.choose_move("synthesis", 105)
    assert action.amount == 48  # Recovery is capped at the missing HP.
    tutorial.complete_action()
    tutorial.confirm()
    assert tutorial.stage == "free_battle"


def test_free_battle_can_win_and_reports_outcome():
    tutorial = GrotleTutorial(rng=LowestRoll())
    tutorial.stage = "free_battle"
    tutorial.foe_hp = 55
    action = tutorial.choose_move("solar_beam", 105)
    assert action.amount == 55
    tutorial.complete_action()
    assert tutorial.outcome == "won"


def test_free_battle_can_lose_and_reset():
    tutorial = GrotleTutorial(rng=HighestRoll())
    tutorial.stage = "enemy_free_announce"
    tutorial.player_hp = 20
    action = tutorial.confirm()
    assert action.amount == 20
    tutorial.complete_action()
    assert tutorial.outcome == "lost"
    tutorial.reset()
    assert tutorial.stage == "intro_absorb"
    assert tutorial.player_hp == tutorial.player_max_hp


def test_light_values_match_the_later_encounters_and_default_to_minimum():
    tutorial = GrotleTutorial()
    assert tutorial.light_values(None) == (70, 30)
    assert tutorial.light_values(0) == (70, 30)
    assert tutorial.light_values(105) == (120, 50)
    assert tutorial.light_values(2048) == (120, 50)


def test_tutorial_damage_uses_authored_random_ranges_and_light_scaling():
    low_roll = GrotleTutorial(rng=LowestRoll())
    high_roll = GrotleTutorial(rng=HighestRoll())
    solar = low_roll.move_spec("solar_beam")
    opponent = low_roll.config["opponent_move"]
    assert low_roll._roll_damage(solar) == 34
    assert high_roll._roll_damage(solar) == 40
    assert low_roll._roll_damage(solar, 120 / 70) == 58
    assert high_roll._roll_damage(solar, 120 / 70) == 69
    assert low_roll._roll_damage(opponent) == 24
    assert high_roll._roll_damage(opponent) == 28


if __name__ == "__main__":
    test_tutorial_unlock_order_and_sensor_ranges()
    test_free_battle_can_win_and_reports_outcome()
    test_free_battle_can_lose_and_reset()
    print("scripted battle ok")
