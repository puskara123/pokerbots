"""legal.py must turn any strategy output into something engine.parse_action accepts."""
import json

from engine.engine import parse_action, parse_discard
from legal import finalize_action, finalize_discard, fallback_action, is_legal_action


def accepted(reply, req):
    action, amount, code = parse_action(json.dumps(reply), req)
    return code is None


FACING_BET = {"legal_actions": ["fold", "call", "raise"], "to_call": 4, "pot": 12,
              "my_bet": 2, "opp_bet": 6, "min_raise": 10, "max_raise": 198}
FREE = {"legal_actions": ["check", "raise"], "to_call": 0, "pot": 12,
        "my_bet": 0, "opp_bet": 0, "min_raise": 2, "max_raise": 194}
CAPPED = {"legal_actions": ["fold", "call"], "to_call": 32, "pot": 68, "my_bet": 18, "opp_bet": 50}
ALLIN_ONLY = {"legal_actions": ["fold", "call", "raise"], "to_call": 10, "pot": 40,
              "my_bet": 5, "opp_bet": 15, "min_raise": 18, "max_raise": 18}


def test_raise_amount_clamped_and_integer():
    assert finalize_action(FACING_BET, "raise", 3)["amount"] == 10
    assert finalize_action(FACING_BET, "raise", 10_000)["amount"] == 198
    r = finalize_action(FACING_BET, "raise", 23.7)
    assert r["amount"] == 24 and isinstance(r["amount"], int) and accepted(r, FACING_BET)


def test_bad_amounts_become_min_raise():
    for bad in (None, "abc", float("nan"), float("inf")):
        r = finalize_action(FACING_BET, "raise", bad)
        assert r["amount"] == 10 and accepted(r, FACING_BET)


def test_raise_when_capped_becomes_call():
    assert finalize_action(CAPPED, "raise", 100) == {"type": "action", "action": "call"}


def test_all_in_below_min_raise():
    r = finalize_action(ALLIN_ONLY, "raise", 50)
    assert r["amount"] == 18 and accepted(r, ALLIN_ONLY)


def test_never_fold_for_free_and_never_check_facing_bet():
    assert finalize_action(FREE, "fold")["action"] == "check"
    assert finalize_action(FREE, "call")["action"] == "check"
    assert finalize_action(FACING_BET, "check")["action"] == "fold"


def test_every_combination_is_accepted():
    for req in (FACING_BET, FREE, CAPPED, ALLIN_ONLY):
        for action in ("fold", "check", "call", "raise", "bogus", None):
            for amount in (None, 0, 5, 18, 300, "x"):
                reply = finalize_action(req, action, amount)
                assert accepted(reply, req) and is_legal_action(reply, req), (req, action, amount)


def test_fallback_without_legal_actions():
    assert fallback_action({"to_call": 0})["action"] == "check"
    assert fallback_action({"to_call": 3})["action"] == "fold"


def test_discard_must_be_own_card():
    req = {"hole_cards": ["7d", "7s", "Ac"]}
    assert finalize_discard(req, "Ac")["card"] == "Ac"
    fixed = finalize_discard(req, "Kh")            # Problem Statement 8.6
    assert fixed["card"] == "7s"
    card, code = parse_discard(json.dumps(fixed), req["hole_cards"])
    assert code is None
    assert finalize_discard(req, None)["card"] == "7s"
