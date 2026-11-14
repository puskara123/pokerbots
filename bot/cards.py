"""Card encoding shared by every module.

Inside the bot a card is an int 0..51:  rank * 4 + suit
    rank 0..12 for 2,3,...,K,A      suit 0..3 for s,h,d,c

Strings like "As" exist only at the protocol boundary (brain.py / legal.py).
Ints are cheaper to hash, compare and do bit tricks on, which matters inside
Monte Carlo loops.

The suit order s,h,d,c is deliberate: it is the engine's tie-break order for the
default discard, so the engine's default discard is simply min() over the ints.
"""

RANKS = "23456789TJQKA"
SUITS = "shdc"

STR_TO_CARD = {r + s: ri * 4 + si for ri, r in enumerate(RANKS) for si, s in enumerate(SUITS)}
CARD_TO_STR = {v: k for k, v in STR_TO_CARD.items()}
FULL_DECK = tuple(range(52))


def parse(card_str):
    """'As' -> 51. Raises KeyError on anything that is not a valid card."""
    return STR_TO_CARD[card_str]


def parse_many(card_strs):
    return [STR_TO_CARD[c] for c in card_strs]


def to_str(card):
    return CARD_TO_STR[card]


def to_strs(cards):
    return [CARD_TO_STR[c] for c in cards]


def rank(card):
    return card >> 2


def suit(card):
    return card & 3


def default_discard_str(hole_strs):
    """The engine's correction rule (Rulebook 9.4): lowest rank, ties broken
    spades, hearts, diamonds, clubs. With our encoding that is just min()."""
    return CARD_TO_STR[min(STR_TO_CARD[c] for c in hole_strs)]
