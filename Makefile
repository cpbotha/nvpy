.PHONY: all
all: format test

.PHONY: format
format:
	yapf -r -p -i .

.PHONY: test
test:
	PYTHONPATH=.:$$PYTHONPATH mypy nvpy tests benchmarks
	PYTHONPATH=.:$$PYTHONPATH python3 -m unittest discover -s tests -p '*.py'

.PHONY: benchmark
benchmark:
	PYTHONPATH=.:$$PYTHONPATH python3 -m nose --with-timer -q -s benchmarks/*.py

.PHONY: docs
docs:
	python3 -m pdoc --http localhost:8080 nvpy
