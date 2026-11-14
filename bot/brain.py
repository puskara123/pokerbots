"""The bot's logic, independent of stdin/stdout.

Brain.on_message(msg: dict) -> reply dict or None

Keeping all logic behind this one method means the same object can be driven
by bot.py (real protocol), by engine/fastsim.py (in-process, thousands of
hands per run) and by unit tests, with no subprocesses or JSON in the way.

Guarantees:
  - a request (action_request / discard_request) ALWAYS gets a legal reply,
    even if the strategy raises: exceptions fall back to legal.fallback_*
  - any other message returns None and can never raise out of here
  - unknown message types and unknown fields are ignored (Protocol 2)
"""
import os
import random
import time

import cards
from debuglog import log
from legal import fallback_action, finalize_action, finalize_discard
from strategy import StrategyV0


class HandState:
    """What we know about the current hand. Cards are ints."""
    __slots__ = ("hand_id", "seat", "hole", "board", "my_discard", "opp_discard")

    def __init__(self, hand_id=None, seat=None, hole=None):
        self.hand_id = hand_id
        self.seat = seat            # "button" / "big_blind" / None if unknown
        self.hole = hole            # list of 3 (later 2) ints, or None if unknown
        self.board = []
        self.my_discard = None
        self.opp_discard = None


class Context:
    """Per-leg facts the strategy may want (time, progress, results so far)."""
    __slots__ = ("total_hands", "hands_done", "time_bank_ms", "time_left_ms",
                 "net", "notices", "max_reply_ms")

    def __init__(self):
        self.total_hands = 200
        self.hands_done = 0
        self.time_bank_ms = None
        self.time_left_ms = None
        self.net = 0
        self.notices = 0
        self.max_reply_ms = 0.0

    @property
    def hands_left(self):
        return max(1, self.total_hands - self.hands_done)


class Brain:
    def __init__(self, strategy=None, seed=None):
        if seed is None and os.environ.get("POKERBOT_SEED"):
            seed = int(os.environ["POKERBOT_SEED"])
        self.rng = random.Random(seed)  # seed=None -> OS entropy
        self.strategy = strategy or StrategyV0(self.rng)
        self.ctx = Context()
        self.hand = HandState()
        self.done = False
        self._handlers = {
            "init": self._on_init,
            "new_hand": self._on_new_hand,
            "discard_result": self._on_discard_result,
            "hand_result": self._on_hand_result,
            "notice": self._on_notice,
            "match_end": self._on_match_end,
        }

    # ------------------------------------------------------------ dispatch
    def on_message(self, msg):
        if not isinstance(msg, dict):
            return None
        t = msg.get("type")
        if t == "action_request":
            return self._timed(self._on_action_request, msg, fallback_action)
        if t == "discard_request":
            return self._timed(self._on_discard_request, msg, self._fallback_discard)
        handler = self._handlers.get(t)
        if handler is not None:
            try:
                handler(msg)
            except Exception as e:  # bad info message: log it, keep playing
                log("info handler error", t, repr(e))
        return None

    def _timed(self, fn, msg, fallback):
        t0 = time.perf_counter()
        try:
            reply = fn(msg)
        except Exception as e:
            log("request error", msg.get("type"), msg.get("hand_id"), repr(e))
            try:
                reply = fallback(msg)
            except Exception:
                reply = {"type": "action", "action": "fold"} \
                    if msg.get("type") == "action_request" else {"type": "discard", "card": "2s"}
        ms = (time.perf_counter() - t0) * 1000.0
        if ms > self.ctx.max_reply_ms:
            self.ctx.max_reply_ms = ms
        return reply

    @staticmethod
    def _fallback_discard(msg):
        return finalize_discard(msg, None)

    # ------------------------------------------------------------ requests
    def _sync_hand(self, msg):
        """Requests carry hand_id; if we somehow missed new_hand, start a blank
        hand so stale cards from a previous hand are never used."""
        if msg.get("hand_id") != self.hand.hand_id:
            self.hand = HandState(msg.get("hand_id"))
        if "board" in msg:
            self.hand.board = cards.parse_many(msg["board"])
        if "time_left_ms" in msg:
            self.ctx.time_left_ms = msg["time_left_ms"]

    def _on_action_request(self, msg):
        self._sync_hand(msg)
        action, amount = self.strategy.act(self.hand, msg, self.ctx)
        return finalize_action(msg, action, amount)

    def _on_discard_request(self, msg):
        self._sync_hand(msg)
        self.hand.hole = cards.parse_many(msg["hole_cards"])  # authoritative copy
        card = self.strategy.discard(self.hand, msg, self.ctx)
        return finalize_discard(msg, cards.to_str(card))

    # -------------------------------------------------------- info messages
    def _on_init(self, msg):
        c = self.ctx
        c.total_hands = int(msg.get("total_hands", c.total_hands))
        c.time_bank_ms = msg.get("time_bank_ms")
        c.time_left_ms = c.time_bank_ms

    def _on_new_hand(self, msg):
        self.hand = HandState(msg.get("hand_id"), msg.get("seat"),
                              cards.parse_many(msg["hole_cards"]))

    def _on_discard_result(self, msg):
        if msg.get("hand_id") != self.hand.hand_id:
            return
        self.hand.my_discard = cards.parse(msg["my_discard"])
        self.hand.opp_discard = cards.parse(msg["opp_discard"])
        self.hand.hole = cards.parse_many(msg["hole_cards"])

    def _on_hand_result(self, msg):
        c = self.ctx
        c.hands_done += 1
        c.net += int(msg.get("net", 0))
        # Saturday: feed msg["history"], opp_hole_cards, opp_discard to opponent.py

    def _on_notice(self, msg):
        self.ctx.notices += 1
        log("NOTICE", msg.get("code"), msg.get("applied"), "hand", self.hand.hand_id)

    def _on_match_end(self, msg):
        self.done = True
        c = self.ctx
        log("leg over:", msg.get("reason"), "hands", c.hands_done, "net", c.net,
            "notices", c.notices, "max reply ms %.1f" % c.max_reply_ms)
