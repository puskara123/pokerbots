# Pokerbots: Discard Hold'em bot

    make test        # unit + fuzz + full in-process matches + short real-engine match
    make sim         # 10 matches each vs starter / random_legal / shove_all (in-process, fast)
    make match       # one real Stage 1 match through the starter engine (logs in results/logs)
    make match2      # one real Stage 2 match
    make package     # build dist/bot.zip and verify it in a read-only directory

Debug output: `POKERBOT_DEBUG=1 make match`, then read results/logs/A_leg1_stderr.txt.
Only `bot/` ships. engine/engine.py is the organisers' starter engine, unmodified.
