"""Turns whatever the strategy wants into a reply the engine will accept.

Every reply passes through here, so a strategy bug can cost a bad decision but
never an engine correction. The rules mirror engine.parse_action /
parse_discard in the starter kit:
  - action must be in legal_actions
  - raise needs an int (not bool) amount with min_raise <= amount <= max_raise
  - a discard must be one of our 3 current hole cards

When the wanted action is not legal we degrade to the closest legal one:
  raise -> call -> check     (wanted to put chips in)
  fold with nothing to call -> check   (never fold for free)
  check when facing a bet -> fold      (what the engine would do anyway)
"""
from cards import STR_TO_CARD, default_discard_str


def fallback_action(req):
    """Safest legal action: check if free, otherwise fold."""
    legal = req.get("legal_actions") if isinstance(req, dict) else None
    if not legal:
        to_call = req.get("to_call", 0) if isinstance(req, dict) else 0
        return {"type": "action", "action": "check" if not to_call else "fold"}
    if "check" in legal:
        return {"type": "action", "action": "check"}
    if "fold" in legal:
        return {"type": "action", "action": "fold"}
    return {"type": "action", "action": legal[0]}


def finalize_action(req, action, amount=None):
    legal = req.get("legal_actions") or []

    if action == "raise":
        if "raise" in legal and "min_raise" in req and "max_raise" in req:
            lo, hi = int(req["min_raise"]), int(req["max_raise"])
            try:
                amt = int(round(float(amount)))
            except (TypeError, ValueError, OverflowError):
                amt = lo
            amt = max(lo, min(hi, amt))
            return {"type": "action", "action": "raise", "amount": amt}
        action = "call" if "call" in legal else "check"

    if action in legal:
        return {"type": "action", "action": action}
    if action in ("fold", "call") and "check" in legal:
        return {"type": "action", "action": "check"}
    return fallback_action(req)


def finalize_discard(req, card):
    hole = req.get("hole_cards") or []
    if isinstance(card, str) and card in hole and card in STR_TO_CARD:
        return {"type": "discard", "card": card}
    valid = [c for c in hole if c in STR_TO_CARD]
    if valid:
        return {"type": "discard", "card": default_discard_str(valid)}
    # Request itself is broken; any string gets the engine's default discard.
    return {"type": "discard", "card": hole[0] if hole else "2s"}


def is_legal_action(reply, req):
    """Test helper: True if the engine would accept this reply unchanged."""
    if not isinstance(reply, dict) or reply.get("type") != "action":
        return False
    a = reply.get("action")
    if a not in (req.get("legal_actions") or []):
        return False
    if a == "raise":
        amt = reply.get("amount")
        if isinstance(amt, bool) or not isinstance(amt, int):
            return False
        return req["min_raise"] <= amt <= req["max_raise"]
    return True
