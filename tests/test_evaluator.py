"""Our fast evaluator must order hands exactly like the starter engine's
best_hand(), which is what decides real showdowns."""
import random

import pytest

import cards
from engine.engine import best_hand as reference
from evaluator import evaluate, category, STRAIGHT, STRAIGHT_FLUSH, FLUSH, FULL_HOUSE, ONE_PAIR


def ours(strs):
    return evaluate(cards.parse_many(strs))


def ref(strs):
    return reference([], strs)  # best 5 of the given cards


DECK = [r + s for r in cards.RANKS for s in cards.SUITS]


@pytest.mark.parametrize("n", [5, 6, 7])
def test_category_and_order_match_reference_random(n):
    rng = random.Random(1234 + n)
    for _ in range(3000):
        drawn = rng.sample(DECK, 2 * n)
        a, b = drawn[:n], drawn[n:]
        va, vb, ra, rb = ours(a), ours(b), ref(a), ref(b)
        assert category(va) == ra[0], (a, va, ra)
        assert (va > vb) == (ra > rb) and (va == vb) == (ra == rb), (a, b)


def test_order_on_shared_board_holdem_style():
    """The situation that actually happens: two 2-card hands, one board."""
    rng = random.Random(7)
    for _ in range(20000):
        d = rng.sample(DECK, 9)
        a, b, board = d[:2], d[2:4], d[4:]
        va, vb = ours(a + board), ours(b + board)
        ra, rb = reference(a, board), reference(b, board)
        assert (va > vb) == (ra > rb) and (va == vb) == (ra == rb), (a, b, board)


def test_wheel_is_lowest_straight():
    wheel = ours(["As", "2d", "3h", "4c", "5s"])
    six_high = ours(["2d", "3h", "4c", "5s", "6d"])
    assert category(wheel) == STRAIGHT and wheel < six_high


def test_no_wraparound_straight():
    assert category(ours(["Qs", "Kd", "Ah", "2c", "3s"])) != STRAIGHT


def test_steel_wheel_and_flush_over_straight():
    assert category(ours(["As", "2s", "3s", "4s", "5s", "Kd", "Kh"])) == STRAIGHT_FLUSH
    assert category(ours(["As", "Js", "8s", "6s", "2s", "7d", "9h"])) == FLUSH


def test_seven_cards_two_trips_is_full_house():
    v = ours(["9s", "9h", "9d", "4s", "4h", "4d", "Ac"])
    assert category(v) == FULL_HOUSE and v > ours(["8s", "8h", "8d", "As", "Ah", "2c", "3d"])


def test_problem_statement_example_8_1_flush_beats_trips():
    board = ["Th", "9h", "2c", "3s", "5h"]
    assert ours(["Qh", "Jh"] + board) > ours(["9s", "9d"] + board)


def test_problem_statement_example_8_5_kicker_and_split():
    board = ["Ah", "Kd", "8c", "5s", "2h"]
    assert ours(["Ac", "Qs"] + board) > ours(["Ad", "Js"] + board)
    board = ["Ts", "Js", "Qd", "Kh", "Ac"]
    assert ours(["9c", "9d"] + board) == ours(["4c", "4h"] + board)  # both play the board


def test_pair_kickers_only_top_three_count():
    board = ["Ah", "Kd", "8c", "5s", "2h"]
    v1 = ours(["Ac", "3d"] + board)  # A A K 8 5 ; the 3 doesn't play
    v2 = ours(["Ad", "4s"] + board)
    assert category(v1) == ONE_PAIR and v1 == v2
