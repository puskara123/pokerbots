"""In-process duplicate-match simulator built on the starter engine.

The starter kit's engine.py already implements the official rules in its Hand
class (betting, min-raise, 4-bet cap, all-in, discard, corrections, showdown).
Hand only needs bot objects with send / begin / wait_reply, so InProcBot below
feeds those calls straight into Brain.on_message: no subprocesses, no pipes,
same rules. Deals are shuffled exactly like engine.py, so a seed gives the
same cards here and in a real `engine.py --seed` run.

    python -m engine.fastsim bot random_legal --matches 10 --deals 200
    python -m engine.fastsim bot starter --matches 5 --seed abc

Bot names: "bot" = bot/brain.Brain, anything else = opponents/<name>.py Brain.
Each leg gets fresh Brain instances, like fresh processes in the real engine.
"""
import argparse
import importlib
import json
import math
import os
import random
import statistics
import sys
import time
from types import SimpleNamespace

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, "bot"), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from engine import engine as E  # noqa: E402
import cards  # noqa: E402
from evaluator import evaluate  # noqa: E402


def _fast_best_hand(hole, board):
    return evaluate(cards.parse_many(list(hole) + list(board)))


class InProcBot:
    """Duck-types engine.Bot for engine.Hand."""

    def __init__(self, name, brain, time_bank_ms):
        self.name = name
        self.brain = brain
        self.notices = 0
        self.time_left_ms = float(time_bank_ms)
        self.time_used_s = 0.0
        self.max_reply_ms = 0.0
        self._line = None

    def _deliver(self, msg):
        # JSON round trip = exactly what a real bot would receive
        return self.brain.on_message(json.loads(json.dumps(msg)))

    def send(self, msg):            # info messages; any reply is ignored, as in the engine
        self._deliver(msg)
        return True

    def begin(self, msg):           # a request: compute the reply now, hand it out in wait_reply
        msg["time_left_ms"] = int(max(0.0, self.time_left_ms))
        t0 = time.perf_counter()
        reply = self._deliver(msg)
        ms = (time.perf_counter() - t0) * 1000.0
        self.time_left_ms -= ms
        self.time_used_s += ms / 1000.0
        self.max_reply_ms = max(self.max_reply_ms, ms)
        try:
            self._line = None if reply is None else json.dumps(reply)
        except (TypeError, ValueError):
            self._line = "<unserialisable reply>"

    def wait_reply(self, wall_deadline):
        if self._line is None:
            return None, "no reply"
        if self.time_left_ms < 0:
            return None, "time bank exhausted"
        return self._line, None


def load_factory(name):
    if name == "bot":
        mod = importlib.import_module("brain")
    else:
        mod = importlib.import_module("opponents." + name)
    return lambda seed=None: mod.Brain(seed=seed)


def run_match(factory_a, factory_b, deals=200, seed="0", time_bank_ms=30_000, fast_eval=True):
    """One match = 2 legs x `deals` hands, hole cards and seats swapped in leg 2.
    Returns a dict; net_a + net_b == 0 unless someone forfeited."""
    original = E.best_hand
    if fast_eval:
        E.best_hand = _fast_best_hand
    totals, notices, used, max_ms = [0, 0], [0, 0], [0.0, 0.0], [0.0, 0.0]
    forfeit = None
    try:
        for leg in range(2):
            bots = (InProcBot("A", factory_a(seed=None), time_bank_ms),
                    InProcBot("B", factory_b(seed=None), time_bank_ms))
            match = SimpleNamespace(bots=bots, wall_deadline=math.inf)
            for b in bots:
                b.send({"type": "init", "protocol_version": "1.0", "total_hands": deals,
                        "starting_stack": E.STARTING_STACK, "small_blind": E.SMALL_BLIND,
                        "big_blind": E.BIG_BLIND, "time_bank_ms": time_bank_ms,
                        "per_response_ms": E.PER_RESPONSE_MS})
            try:
                for deal in range(deals):
                    deck = [r + s for r in E.RANKS for s in E.SUITS]
                    random.Random(f"{seed}:{deal}").shuffle(deck)   # same as engine.py
                    button = (deal + leg) % 2
                    hand = E.Hand(match, deal + 1, button, (deck[0:3], deck[3:6]), deck[6:11])
                    nets = hand.play()
                    totals[button] += nets[0]
                    totals[1 - button] += nets[1]
            except E.Forfeit as f:
                forfeit = [(b.name, reason, leg + 1) for b, reason in f.failures]
            finally:
                for k, b in enumerate(bots):
                    b.send({"type": "match_end", "reason": "complete" if not forfeit else "forfeit"})
                    notices[k] += b.notices
                    used[k] += b.time_used_s
                    max_ms[k] = max(max_ms[k], b.max_reply_ms)
            if forfeit:
                break
    finally:
        E.best_hand = original
    return {"net_a": totals[0], "net_b": totals[1], "notices": notices, "forfeit": forfeit,
            "time_used_s": used, "max_reply_ms": max_ms}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("bot_a")
    p.add_argument("bot_b")
    p.add_argument("--matches", type=int, default=5)
    p.add_argument("--deals", type=int, default=200, help="deals per leg (200 = Stage 1)")
    p.add_argument("--seed", default="sim", help="base seed; match i uses '<seed>-<i>'")
    p.add_argument("--reference-eval", action="store_true",
                   help="use the starter engine's slow evaluator for showdowns")
    a = p.parse_args()

    fa, fb = load_factory(a.bot_a), load_factory(a.bot_b)
    w = d = l = 0
    nets = []
    t0 = time.perf_counter()
    for i in range(a.matches):
        r = run_match(fa, fb, a.deals, f"{a.seed}-{i}", fast_eval=not a.reference_eval)
        nets.append(r["net_a"])
        if r["forfeit"]:
            print(f"match {i}: FORFEIT {r['forfeit']}")
        res = "W" if r["net_a"] > r["net_b"] else "L" if r["net_a"] < r["net_b"] else "D"
        w, d, l = w + (res == "W"), d + (res == "D"), l + (res == "L")
        print(f"match {i:3d}: {res} net A {r['net_a']:+6d}  notices A/B {r['notices']}  "
              f"A time {r['time_used_s'][0]:.2f}s  A max reply {r['max_reply_ms'][0]:.1f}ms")
    hands = 2 * a.deals
    per_hand = [n / hands for n in nets]
    mean = statistics.fmean(per_hand)
    half = 1.96 * statistics.stdev(per_hand) / math.sqrt(len(per_hand)) if len(per_hand) > 1 else float("nan")
    print(f"\n{a.bot_a} vs {a.bot_b}: W/D/L {w}/{d}/{l}   chips/hand {mean:+.3f} ± {half:.3f} (95%)"
          f"   [{time.perf_counter() - t0:.1f}s]")


if __name__ == "__main__":
    main()
