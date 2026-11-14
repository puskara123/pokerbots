"""Maniac opponent: shoves every hand, calls any bet. Exercises all-in paths
(discard with no betting, no requests on later streets) and our calling ranges."""
import sys, json


def choose_action(req):
    legal = req["legal_actions"]
    if "raise" in legal:
        return {"type": "action", "action": "raise", "amount": req["max_raise"]}
    if "call" in legal:
        return {"type": "action", "action": "call"}
    return {"type": "action", "action": "check"}


def choose_discard(req):
    return {"type": "discard", "card": req["hole_cards"][0]}


class Brain:
    """In-process adapter for engine/fastsim.py."""
    def __init__(self, seed=None):
        pass

    def on_message(self, msg):
        t = msg.get("type")
        if t == "action_request":
            return choose_action(msg)
        if t == "discard_request":
            return choose_discard(msg)
        return None


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if msg.get("type") == "match_end":
            break
        reply = Brain().on_message(msg)
        if reply is not None:
            print(json.dumps(reply), flush=True)


if __name__ == "__main__":
    main()
