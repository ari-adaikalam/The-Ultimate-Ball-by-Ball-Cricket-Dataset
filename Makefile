PY := .venv/bin/python

.PHONY: setup test status ingest verify players

setup:
	python3 -m venv .venv
	$(PY) -m pip install -q -e ".[dev]"

test:
	$(PY) -m pytest -q

# Lists matches on Cricsheet that the dataset does not have yet
status:
	$(PY) -m cricket_pipeline status

# Builds Cricsheet rows for matches the published dataset lacks, one file per archive in data/work/
ingest:
	$(PY) -m cricket_pipeline ingest

# Rebuilds a sample of known matches and diffs them against the published dataset
verify:
	$(PY) -m cricket_pipeline verify --sample 100

# Fetches Cricinfo player profiles through a Chrome started with --remote-debugging-port=9222 (see cricket_pipeline/scrape_players.py)
players:
	$(PY) -m cricket_pipeline players

