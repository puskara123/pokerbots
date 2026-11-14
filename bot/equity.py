"""How strong is my hand?  v0: fast heuristics.

Interface the strategy relies on (keep it stable; Thursday swaps the internals):
    preflop_strength(hole3)        -> percentile in [0, 1] among all 3-card hands
    keep_strength(keep2, board)    -> (strength in [0, 1], has_draw)
    flop_strength(hole3, flop)     -> (best keep strength, has_draw, best keep)

Thursday: preflop_strength reads the precomputed discard-aware equity table
(preflop_table.py), and keep_strength becomes Monte Carlo equity against a
weighted opponent range. Until then these numbers are rough "equity-like"
scores, calibrated by hand so that pot-odds comparisons in strategy.py are sane.
"""
from itertools import combinations

from evaluator import evaluate, STRAIGHT_HIGH, FLUSH, STRAIGHT, TRIPS, FULL_HOUSE

# ---------------------------------------------------------------- preflop

_CHEN_HIGH = (1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 6, 7, 8, 10)  # 2..A


def _chen(a, b):
    """Chen formula for a 2-card hand (published heuristic)."""
    ra, rb = a >> 2, b >> 2
    if ra < rb:
        ra, rb = rb, ra
    if ra == rb:
        return max(5.0, _CHEN_HIGH[ra] * 2)
    s = _CHEN_HIGH[ra]
    if (a & 3) == (b & 3):
        s += 2
    gap = ra - rb - 1
    s -= (0, 1, 2, 4)[gap] if gap < 4 else 5
    if gap <= 1 and ra < 10:  # connected/one-gap below a queen
        s += 1
    return s


def _score3(hole):
    """Best 2-card subset dominates; the other subsets add flexibility (a 3-card
    hand picks its best 2 after seeing the flop)."""
    s = sorted((_chen(a, b) for a, b in combinations(hole, 2)), reverse=True)
    return s[0] + 0.3 * s[1] + 0.15 * s[2]


def _build_percentiles():
    scores = {h: _score3(h) for h in combinations(range(52), 3)}
    ordered = sorted(scores.values())
    n = len(ordered)
    # percentile of a score = share of hands strictly below + half the ties
    first, last = {}, {}
    for i, v in enumerate(ordered):
        first.setdefault(v, i)
        last[v] = i
    pct_of = {v: (first[v] + 0.5 * (last[v] - first[v] + 1)) / n for v in first}
    return {h: pct_of[v] for h, v in scores.items()}


# 22,100 entries, built at import (~0.2 s) inside the uncharged start-up window.
_PREFLOP_PCT = _build_percentiles()


def preflop_strength(hole3):
    return _PREFLOP_PCT[tuple(sorted(hole3))]


# --------------------------------------------------------------- postflop

def _counts(ranks):
    c = [0] * 13
    for r in ranks:
        c[r] += 1
    return c


def draw_info(keep, board):
    """(flush_draw, straight_outs) where our hole cards take part in the draw.
    straight_outs = number of ranks that would complete a straight using a
    hole card: 2 ~ open-ended, 1 ~ gutshot."""
    cards = list(keep) + list(board)
    flush_draw = False
    for s in range(4):
        if sum(1 for c in cards if c & 3 == s) == 4 and any(c & 3 == s for c in keep):
            flush_draw = True
    mask = bmask = 0
    for c in cards:
        mask |= 1 << (c >> 2)
    for c in board:
        bmask |= 1 << (c >> 2)
    outs = 0
    if not STRAIGHT_HIGH[mask]:
        for r in range(13):
            if not mask >> r & 1:
                hi = STRAIGHT_HIGH[mask | 1 << r]
                if hi and hi > STRAIGHT_HIGH[bmask | 1 << r]:
                    outs += 1
    return flush_draw, outs


def _pair_strength(kr, br):
    """kr: our 2 ranks (desc), br: board ranks. One-pair-ish situations."""
    ranked = sorted(set(br), reverse=True)
    top = ranked[0]
    if kr[0] == kr[1] and kr[0] not in br:            # pocket pair
        above = sum(1 for r in ranked if r > kr[0])
        if above == 0:
            return 0.70 + 0.004 * kr[0]               # overpair
        return max(0.30, 0.50 - 0.07 * (above - 1))   # underpair
    hits = [r for r in set(kr) if r in br]
    board_paired = len(ranked) < len(br)
    if len(hits) == 2:                                # two pair with both hole cards
        return 0.55 if board_paired else 0.78
    if hits:
        h = hits[0]
        kicker = kr[1] if kr[0] == h else kr[0]
        idx = ranked.index(h)
        if idx == 0:
            return 0.58 + 0.01 * kicker               # top pair, kicker matters
        if idx == 1:
            return 0.46 + 0.004 * kicker
        return 0.38
    overs = sum(1 for r in kr if r > top)             # no pair of our own
    return 0.10 + 0.05 * overs + 0.004 * kr[0]


def keep_strength(keep, board):
    """Heuristic equity-like score of 2 hole cards on a 3-5 card board."""
    keep, board = list(keep), list(board)
    v = evaluate(keep + board)
    if len(board) == 5 and v == evaluate(board):
        return 0.10, False                            # playing the board
    cat = v >> 20
    kr = sorted((c >> 2 for c in keep), reverse=True)
    br = [c >> 2 for c in board]
    board_max_count = max(_counts(br))

    if cat >= FULL_HOUSE:
        s = 0.95
    elif cat in (FLUSH, STRAIGHT):
        s = 0.80 if board_max_count >= 2 else 0.88    # paired board: full houses exist
    elif cat == TRIPS:
        s = 0.85 if board_max_count < 3 else 0.25 + 0.01 * kr[0]
    else:
        s = _pair_strength(kr, br)

    has_draw = False
    if len(board) < 5:
        flush_draw, outs = draw_info(keep, board)
        flop = len(board) == 3
        bonus = 0.0
        if flush_draw:
            bonus += 0.18 if flop else 0.10
        if outs >= 2:
            bonus += 0.12 if flop else 0.07
        elif outs == 1:
            bonus += 0.05 if flop else 0.03
        has_draw = flush_draw or outs >= 2
        s += bonus * (1.0 - s)                        # diminishing for made hands
    return min(s, 0.99), has_draw


def flop_strength(hole3, flop):
    """Before the discard we hold 3 cards but will keep the best 2, so our
    flop strength is the best of the three keeps. The same numbers decide the
    discard, so discard.py calls this too (Thursday: cached per hand)."""
    best = None
    for keep in combinations(hole3, 2):
        s, d = keep_strength(keep, flop)
        key = (s, sum(c >> 2 for c in keep))          # tie-break: keep higher ranks
        if best is None or key > best[0]:
            best = (key, s, d, keep)
    return best[1], best[2], list(best[3])
