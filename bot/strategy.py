"""Betting and discard policy.

The strategy only *suggests* (action, amount); brain.py passes the suggestion
through legal.py, so nothing here can produce an illegal reply.

v0 logic, deliberately simple and readable:
  preflop  - percentile of the 3-card hand, thresholds by situation
  postflop - heuristic strength compared with the pot odds of a call
  sizing   - pot fractions: "call, then raise `frac` of the resulting pot"
Every threshold lives in PARAMS so Saturday's tuning edits one dict.
"""
from discard import choose_discard
from equity import preflop_strength, keep_strength, flop_strength

PARAMS = {
    # preflop, as percentiles of all 3-card hands (1.0 = best)
    "open_raise": 0.30,      # button: raise to 5 with the top 70%
    "open_limp": 0.15,       # button: limp the next 15%, fold the rest
    "open_size": 5,          # raise-to amount (2.5 big blinds)
    "iso_raise": 0.70,       # big blind after a limp: raise top 30%
    "reraise": 0.90,         # facing a raise: re-raise top 10%
    "jam": 0.97,             # facing a raise: shove top 3%
    # preflop call rule: call if 0.33 + 0.34*pct >= price + margin
    "pf_eq_base": 0.33, "pf_eq_span": 0.34,
    "pf_margin": 0.03, "pf_margin_per_chip": 0.06 / 200,
    # postflop
    "value_bet": 0.70, "value_size": 0.66,
    "thin_bet": 0.52, "thin_freq": 0.35, "thin_size": 0.33,
    "semibluff_freq": 0.45, "semibluff_size": 0.5,
    "bluff_max": 0.25, "bluff_freq": 0.07, "bluff_size": 0.66,
    "raise_value": 0.85, "raise_size": 0.8,
    "call_margin": 0.08, "draw_call_price": 0.30,
    "jam_fraction": 0.65,    # if a raise would commit >=65% of max, just shove
}


def size_to(req, frac):
    """Raise-to amount for a pot-fraction raise: call first, then add
    `frac` x (pot after the call). With nothing to call it is a plain bet."""
    pot_after_call = req["pot"] + req["to_call"]
    return req["opp_bet"] + frac * pot_after_call


def maybe_jam(req, amount):
    hi = req.get("max_raise")
    if hi is not None and amount >= PARAMS["jam_fraction"] * hi:
        return hi
    return amount


class StrategyV0:
    def __init__(self, rng):
        self.rng = rng

    # -------------------------------------------------------------- actions
    def act(self, hand, req, ctx):
        """hand: brain.HandState, req: action_request dict, ctx: brain.Context.
        Returns (action, amount_or_None)."""
        if hand.hole is None:
            return "check", None  # we never saw our cards; legal.py makes it check/fold
        if req["street"] == "preflop":
            return self._preflop(hand, req)
        return self._postflop(hand, req)

    def _preflop(self, hand, req):
        P = PARAMS
        pct = preflop_strength(hand.hole)
        to_call, legal = req["to_call"], req["legal_actions"]
        first_in = hand.seat == "button" and req["my_bet"] == 1 and req["opp_bet"] == 2

        if first_in:
            if pct >= P["open_raise"]:
                return "raise", P["open_size"]
            return ("call", None) if pct >= P["open_limp"] else ("fold", None)

        if to_call == 0:  # big blind's option after a limp
            if pct >= P["iso_raise"]:
                return "raise", size_to(req, 1.0)
            return "check", None

        if pct >= P["jam"] and "raise" in legal:
            return "raise", req["max_raise"]
        if pct >= P["reraise"] and "raise" in legal:
            return "raise", maybe_jam(req, size_to(req, 1.0))
        price = to_call / (req["pot"] + to_call)
        equity = P["pf_eq_base"] + P["pf_eq_span"] * pct
        margin = P["pf_margin"] + P["pf_margin_per_chip"] * to_call
        return ("call", None) if equity >= price + margin else ("fold", None)

    def _postflop(self, hand, req):
        P = PARAMS
        if len(hand.hole) == 3:
            s, has_draw, _ = flop_strength(hand.hole, hand.board)
        else:
            s, has_draw = keep_strength(hand.hole, hand.board)
        river = req["street"] == "river"
        rnd = self.rng.random()

        if req["to_call"] == 0:
            if s >= P["value_bet"]:
                return "raise", maybe_jam(req, size_to(req, P["value_size"]))
            if has_draw and not river and rnd < P["semibluff_freq"]:
                return "raise", size_to(req, P["semibluff_size"])
            if s >= P["thin_bet"] and rnd < P["thin_freq"]:
                return "raise", size_to(req, P["thin_size"])
            if s < P["bluff_max"] and rnd < P["bluff_freq"]:
                return "raise", size_to(req, P["bluff_size"])
            return "check", None

        price = req["to_call"] / (req["pot"] + req["to_call"])
        if s >= P["raise_value"] and "raise" in req["legal_actions"]:
            return "raise", maybe_jam(req, size_to(req, P["raise_size"]))
        if s >= price + P["call_margin"]:
            return "call", None
        if has_draw and not river and price <= P["draw_call_price"]:
            return "call", None
        return "fold", None

    # -------------------------------------------------------------- discard
    def discard(self, hand, req, ctx):
        """Returns the card int to discard (hole/board already parsed)."""
        return choose_discard(hand.hole, hand.board)
