"""Fast exact evaluator for 5, 6 or 7 cards (ints from cards.py).

evaluate(cards) returns one int; a bigger int is a better hand, equal ints tie.
Layout:  category << 20 | payload, where payload packs up to five 4-bit ranks.

Why not the starter kit's evaluator? engine.best_hand() scores all 21 five-card
subsets of 7 cards with a Counter each. It is correct (we use it as the
reference in tests) but ~20x slower. Here we look at the 7 cards once:
per-rank counts, one 13-bit mask per suit and one for all ranks, then lookup
tables for straights and top-k ranks. Tables are built once at import, during
the uncharged start-up window.

Correctness note: with at most 7 cards a flush can never coexist with quads or
a full house (it would need 8+ cards), so checking the flush first is safe.
"""

HIGH_CARD, ONE_PAIR, TWO_PAIR, TRIPS, STRAIGHT, FLUSH, FULL_HOUSE, QUADS, STRAIGHT_FLUSH = range(9)
CATEGORY_NAMES = ("high card", "one pair", "two pair", "three of a kind", "straight",
                  "flush", "full house", "four of a kind", "straight flush")
_SHIFT = 20

# STRAIGHT_HIGH[mask] = (index of the straight's top card) + 1, or 0 if no straight.
# The wheel A-2-3-4-5 has top card 5 (index 3) -> 4, the lowest possible straight.
STRAIGHT_HIGH = [0] * 8192
for _m in range(8192):
    for _hi in range(12, 3, -1):
        _w = 0b11111 << (_hi - 4)
        if _m & _w == _w:
            STRAIGHT_HIGH[_m] = _hi + 1
            break
    else:
        if _m & 0x100F == 0x100F:  # A,2,3,4,5
            STRAIGHT_HIGH[_m] = 4

# DESC[mask] = ranks present in mask, highest first.
DESC = [tuple(r for r in range(12, -1, -1) if _m >> r & 1) for _m in range(8192)]


def _pack(ranks, k):
    """First k ranks as k 4-bit nibbles, most significant first."""
    v = 0
    for r in ranks[:k]:
        v = (v << 4) | r
    return v


TOP5 = [_pack(d, 5) if len(d) >= 5 else 0 for d in DESC]
del _m, _hi, _w


def evaluate(cards):
    counts = [0] * 13
    sm = [0, 0, 0, 0]
    for c in cards:
        r = c >> 2
        counts[r] += 1
        sm[c & 3] |= 1 << r

    for m in sm:
        if m.bit_count() >= 5:
            s = STRAIGHT_HIGH[m]
            if s:
                return (STRAIGHT_FLUSH << _SHIFT) | s
            return (FLUSH << _SHIFT) | TOP5[m]

    rank_mask = sm[0] | sm[1] | sm[2] | sm[3]
    quad = trip = -1
    pairs = []  # descending; a second set of trips also counts as a pair (full house)
    for r in range(12, -1, -1):
        n = counts[r]
        if n == 4:
            quad = r
        elif n == 3:
            if trip < 0:
                trip = r
            else:
                pairs.append(r)
        elif n == 2:
            pairs.append(r)

    if quad >= 0:
        kicker = (rank_mask & ~(1 << quad)).bit_length() - 1
        return (QUADS << _SHIFT) | (quad << 4) | kicker
    if trip >= 0 and pairs:
        return (FULL_HOUSE << _SHIFT) | (trip << 4) | pairs[0]
    s = STRAIGHT_HIGH[rank_mask]
    if s:
        return (STRAIGHT << _SHIFT) | s
    if trip >= 0:
        k = DESC[rank_mask & ~(1 << trip)]
        return (TRIPS << _SHIFT) | (trip << 8) | (k[0] << 4) | k[1]
    if len(pairs) >= 2:
        p1, p2 = pairs[0], pairs[1]
        kicker = (rank_mask & ~(1 << p1) & ~(1 << p2)).bit_length() - 1
        return (TWO_PAIR << _SHIFT) | (p1 << 8) | (p2 << 4) | kicker
    if pairs:
        p = pairs[0]
        return (ONE_PAIR << _SHIFT) | (p << 12) | _pack(DESC[rank_mask & ~(1 << p)], 3)
    return (HIGH_CARD << _SHIFT) | TOP5[rank_mask]


def category(value):
    return value >> _SHIFT


def category_name(value):
    return CATEGORY_NAMES[value >> _SHIFT]
