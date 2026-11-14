"""The brain must answer every request legally, ignore everything else, and
survive garbage. Oracle = the starter engine's own parse_action/parse_discard."""
import json
import os
import random
import subprocess
import sys

import pytest

import cards
from brain import Brain
from engine.engine import parse_action, parse_discard
from engine.fastsim import run_match, load_factory

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DECK = [r + s for r in cards.RANKS for s in cards.SUITS]


def check_action(reply, req):
    _, _, code = parse_action(json.dumps(reply), req)
    assert code is None, (reply, req)


def test_protocol_example_hand():
    """Protocol Specification section 10, message by message."""
    b = Brain(seed=1)
    assert b.on_message({"type": "init", "protocol_version": "1.0", "total_hands": 200,
                         "starting_stack": 200, "small_blind": 1, "big_blind": 2,
                         "time_bank_ms": 30000, "per_response_ms": 5000}) is None
    assert b.on_message({"type": "new_hand", "hand_id": 1, "seat": "button",
                         "hole_cards": ["As", "Kd", "7c"], "stack": 200, "opp_stack": 200}) is None
    req = {"type": "action_request", "hand_id": 1, "street": "preflop", "board": [], "pot": 3,
           "my_bet": 1, "opp_bet": 2, "to_call": 1, "my_stack": 199, "opp_stack": 198,
           "legal_actions": ["fold", "call", "raise"], "min_raise": 4, "max_raise": 200,
           "raises_left": 3, "history": [], "time_left_ms": 30000}
    check_action(b.on_message(req), req)
    req = {"type": "action_request", "hand_id": 1, "street": "flop", "board": ["Ah", "7d", "2s"],
           "pot": 12, "my_bet": 0, "opp_bet": 0, "to_call": 0, "my_stack": 194, "opp_stack": 194,
           "legal_actions": ["check", "raise"], "min_raise": 2, "max_raise": 194, "raises_left": 4,
           "history": [], "time_left_ms": 29940}
    check_action(b.on_message(req), req)
    dreq = {"type": "discard_request", "hand_id": 1, "hole_cards": ["As", "Kd", "7c"],
            "board": ["Ah", "7d", "2s"], "pot": 24, "my_stack": 188, "opp_stack": 188,
            "time_left_ms": 29900}
    d = b.on_message(dreq)
    assert parse_discard(json.dumps(d), dreq["hole_cards"])[1] is None
    assert d["card"] == "Kd"  # keep A+7 = two pair on A-7-2
    b.on_message({"type": "discard_result", "hand_id": 1, "my_discard": "Kd",
                  "opp_discard": "Qs", "hole_cards": ["As", "7c"]})
    assert b.hand.hole == cards.parse_many(["As", "7c"])
    assert b.on_message({"type": "hand_result", "hand_id": 1, "result": "fold", "net": 12,
                         "board": [], "my_hole_cards": ["As", "7c"], "opp_hole_cards": None,
                         "opp_discard": "Qs", "history": []}) is None
    assert b.ctx.net == 12 and b.ctx.hands_done == 1


def random_request(rng):
    """A random but internally consistent action_request, built with the
    engine's own formulas for legal actions and min/max raise."""
    street = rng.choice(["preflop", "flop", "turn", "river"])
    n_board = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}[street]
    dealt = rng.sample(DECK, 3 + n_board)
    committed_before = 0 if street == "preflop" else rng.choice([2, 6, 20, 60, 150])
    stack = 200 - committed_before
    opp_bet = rng.choice([0, 0, 2, 4, 10, 30, stack]) if street != "preflop" else rng.choice([2, 6, 18, 50, 200])
    opp_bet = min(opp_bet, stack)
    my_bet = rng.choice([b for b in (0, 1, 2, opp_bet) if b <= opp_bet])
    if street == "preflop":
        my_bet = max(my_bet, 1)
    to_call = opp_bet - my_bet
    last_raise = max(2, opp_bet - my_bet) if opp_bet else 0
    raises = rng.randint(0, 4)
    max_raise = stack
    legal = ["fold", "call"] if to_call > 0 else ["check"]
    can_raise = raises < 4 and max_raise > opp_bet
    req = {"type": "action_request", "hand_id": 1, "street": street, "board": dealt[3:],
           "pot": 2 * committed_before + my_bet + opp_bet, "my_bet": my_bet, "opp_bet": opp_bet,
           "to_call": to_call, "my_stack": stack - my_bet, "opp_stack": stack - opp_bet,
           "legal_actions": legal + (["raise"] if can_raise else []),
           "raises_left": 4 - raises, "history": [], "time_left_ms": 20000}
    if can_raise:
        req["min_raise"] = min(opp_bet + max(last_raise, 2), max_raise)
        req["max_raise"] = max_raise
    hole = dealt[:3] if street in ("preflop", "flop") else dealt[:2]
    return req, hole


def test_fuzz_random_requests_always_legal():
    rng = random.Random(99)
    b = Brain(seed=3)
    for i in range(3000):
        req, hole = random_request(rng)
        req["hand_id"] = i
        b.on_message({"type": "new_hand", "hand_id": i, "seat": rng.choice(["button", "big_blind"]),
                      "hole_cards": hole, "stack": 200, "opp_stack": 200})
        check_action(b.on_message(req), req)


@pytest.mark.parametrize("drop", ["legal_actions", "pot", "to_call", "board", "min_raise",
                                  "street", "opp_bet", "hand_id"])
def test_missing_fields_never_crash(drop):
    rng = random.Random(5)
    b = Brain(seed=4)
    for i in range(200):
        req, hole = random_request(rng)
        b.on_message({"type": "new_hand", "hand_id": 1, "seat": "button", "hole_cards": hole})
        req.pop(drop, None)
        reply = b.on_message(req)
        assert reply["type"] == "action" and reply["action"] in ("fold", "check", "call", "raise")
        json.dumps(reply)


def test_garbage_and_unknown_messages():
    b = Brain(seed=5)
    for msg in ({"type": "weird"}, {"type": "notice", "code": "malformed", "applied": "fold"},
                {"no_type": 1}, {"type": "new_hand", "hole_cards": ["Zz", "1x", "As"]},
                {"type": "discard_result", "hand_id": 77}, {"type": "hand_result", "net": "abc"}):
        assert b.on_message(msg) is None
    req = {"type": "discard_request", "hand_id": 9, "hole_cards": ["2s", "Zz"], "board": []}
    reply = b.on_message(req)
    assert reply["type"] == "discard"
    # action with no new_hand at all: still legal
    req, _ = random_request(random.Random(1))
    req["hand_id"] = 12345
    check_action(Brain(seed=6).on_message(req), req)


@pytest.mark.parametrize("opponent", ["random_legal", "starter", "shove_all"])
def test_full_stage1_match_in_process(opponent):
    r = run_match(load_factory("bot"), load_factory(opponent), deals=200, seed=f"t-{opponent}")
    assert r["forfeit"] is None
    assert r["notices"][0] == 0, r
    assert r["net_a"] + r["net_b"] == 0


def test_real_subprocess_match_short():
    """bot.py through the real starter engine: pipes, flushing, exit after match_end."""
    out = subprocess.run(
        [sys.executable, os.path.join(ROOT, "engine", "engine.py"),
         os.path.join(ROOT, "bot", "bot.py"), os.path.join(ROOT, "opponents", "random_legal.py"),
         "--hands", "40", "--seed", "t", "--log-dir", ""],
        capture_output=True, text=True, timeout=120)
    assert "forfeit" not in out.stdout, out.stdout
    line_a = [l for l in out.stdout.splitlines() if l.strip().startswith("A ")][0]
    assert line_a.rstrip().endswith("notices 0"), out.stdout
