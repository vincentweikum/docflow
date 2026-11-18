.PHONY: all data run evaluate test lint
all: test evaluate

data:       ## generate 250 invoices + answer key, and scanned copies
	python -c "from pathlib import Path; from docflow.generate import generate; from docflow.scan import make_scans; generate(Path('data/invoices')); make_scans(Path('data/invoices'), Path('data/scanned'))"

run:        ## extract + validate a folder, write clean tables to out/
	python -m docflow.pipeline data/invoices out

evaluate:   ## score clean and scanned sets against the answer key
	python -m docflow.evaluate

test:
	pytest -q

lint:
	ruff check .
