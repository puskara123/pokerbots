"""Time governor.

The bank is per leg and cumulative (30 s / 200 hands in Stage 1, 75 s / 500 in
Stage 2): both are 150 ms per hand, spread over up to ~6 requests. The official
vCPU may be slower than a laptop, so we spend only a fraction of the fair share.

v0 does no heavy computation, so this module only matters from Thursday on,
when Monte Carlo loops take a Deadline and stop when it expires. It is written
now so the brain already tracks the numbers it needs (time_left_ms, hands left).
"""
import time

SAFETY = 0.4          # spend at most 40% of the fair share per hand
HARD_CAP_MS = 1500    # never plan more than this for one reply (limit is 5000)
PANIC_MS = 3000       # below this bank, strategies should use table-only play


def budget_ms(time_left_ms, hands_left, weight=1.0):
    """Milliseconds this request may use. `weight` lets important decisions
    (e.g. the flop) take more than cheap ones (preflop lookups)."""
    if time_left_ms is None:
        return 50.0
    hands_left = max(1, hands_left)
    fair = time_left_ms / hands_left
    return max(0.0, min(HARD_CAP_MS, SAFETY * fair * weight))


def panic(time_left_ms):
    return time_left_ms is not None and time_left_ms < PANIC_MS


class Deadline:
    """Usage in a loop:  dl = Deadline(ms); while not dl.expired(): ..."""
    __slots__ = ("end",)

    def __init__(self, ms):
        self.end = time.perf_counter() + ms / 1000.0

    def expired(self):
        return time.perf_counter() >= self.end

    def remaining_ms(self):
        return max(0.0, (self.end - time.perf_counter()) * 1000.0)
