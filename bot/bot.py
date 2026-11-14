"""Pokerbots entry point: python3.11 bot.py

Only plumbing lives here: read one JSON line from stdin, hand it to the
Brain, write the reply as one flushed JSON line on stdout. Everything that can
go wrong is contained so the process never dies mid-leg (a crash forfeits the
whole match, Rulebook 9.1).
"""
import os
import sys

# Must run before anything imports numpy: one vCPU, so no BLAS thread pools.
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_var, "1")
sys.dont_write_bytecode = True  # read-only filesystem: don't even try to write .pyc

# Our modules sit next to this file (in the repo's bot/ folder and at the top
# level of the zip). Don't rely on the working directory the server uses.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import json

_RANKS = "23456789TJQKA"
_SUITS = "shdc"


class _FallbackBrain:
    """Used only if our own modules fail to import or a reply cannot be built.
    Self-contained on purpose: no imports from our code, always legal."""

    def on_message(self, msg):
        t = msg.get("type")
        if t == "action_request":
            legal = msg.get("legal_actions") or []
            if "check" in legal:
                return {"type": "action", "action": "check"}
            return {"type": "action", "action": "fold" if "fold" in legal or not legal else legal[0]}
        if t == "discard_request":
            hole = [c for c in (msg.get("hole_cards") or [])
                    if isinstance(c, str) and len(c) == 2 and c[0] in _RANKS and c[1] in _SUITS]
            card = min(hole, key=lambda c: (_RANKS.index(c[0]), _SUITS.index(c[1]))) if hole else "2s"
            return {"type": "discard", "card": card}
        return None


_fallback = _FallbackBrain()
try:
    from brain import Brain
    _brain = Brain()
except Exception as _e:  # noqa: BLE001 - any import/startup failure
    sys.stderr.write("brain unavailable, using fallback: %r\n" % (_e,))
    _brain = _fallback


def _write(reply):
    sys.stdout.write(json.dumps(reply, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main():
    readline = sys.stdin.readline
    while True:
        line = readline()
        if not line:          # EOF: the engine closed our stdin
            return
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if not isinstance(msg, dict):
            continue
        try:
            reply = _brain.on_message(msg)
        except Exception:     # Brain already guards itself; this is belt and braces
            reply = _fallback.on_message(msg)
        if reply is not None:
            try:
                _write(reply)
            except (BrokenPipeError, OSError):
                return
            except (TypeError, ValueError):  # reply not serialisable
                _write(_fallback.on_message(msg))
        if msg.get("type") == "match_end":
            return


if __name__ == "__main__":
    main()
