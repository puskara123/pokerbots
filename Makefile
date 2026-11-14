PY ?= python3.11

.PHONY: test sim match match2 package

test:
	$(PY) -m pytest -q

sim:
	$(PY) -m engine.fastsim bot starter --matches 10
	$(PY) -m engine.fastsim bot random_legal --matches 10
	$(PY) -m engine.fastsim bot shove_all --matches 10

match:
	$(PY) engine/engine.py bot/bot.py opponents/starter.py --log-dir results/logs

match2:
	$(PY) engine/engine.py bot/bot.py opponents/random_legal.py --stage 2 --log-dir results/logs2

package:
	$(PY) tools/package.py --python $(PY)
