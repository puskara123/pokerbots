"""Discard decision.

v0: keep the 2 cards with the best keep_strength on the flop (made hand plus
draw bonus), tie-broken towards higher ranks. That alone beats the starter
bot's "throw the lowest rank", which happily breaks up pairs and flush draws.

Thursday: replace the heuristic with Monte Carlo keep-equities against a
sampled opponent who also discards, and add opponent_discard_likelihood()
for the post-discard range update.
"""
from equity import flop_strength


def choose_discard(hole3, flop):
    """hole3, flop: card ints. Returns the card int to throw away."""
    _, _, keep = flop_strength(hole3, flop)
    for c in hole3:
        if c not in keep:
            return c
    return min(hole3)  # unreachable with 3 distinct cards; defensive
