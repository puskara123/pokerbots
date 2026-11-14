"""Debug logging to stderr, off by default and hard-capped.

- Never stdout: a stray stdout line while a request is outstanding is taken as
  the reply (Protocol 2), so every print would become a check/fold.
- Never files: the filesystem is read-only (Rulebook 5.4).
- Capped well below 64 KB: the engine only keeps 64 KB of stderr per leg. The
  starter engine keeps reading after that, but if the official one stopped
  reading, the pipe would fill, our write would block, and we would time out.

Enable locally with:  POKERBOT_DEBUG=1 python3.11 engine/engine.py ...
(the engine starts bots with the parent's environment).
"""
import os
import sys

ENABLED = os.environ.get("POKERBOT_DEBUG") == "1"
LIMIT_BYTES = 32 * 1024
_written = 0


def log(*parts):
    global _written
    if not ENABLED or _written >= LIMIT_BYTES:
        return
    data = (" ".join(str(p) for p in parts) + "\n").encode("utf-8", "replace")
    data = data[:LIMIT_BYTES - _written]
    _written += len(data)
    try:
        sys.stderr.write(data.decode("utf-8", "ignore"))
        sys.stderr.flush()
    except Exception:
        pass
