.PHONY: all
all: format test

.PHONY: format
format:
	yapf -r -p -i .

.PHONY: test
test:
	PYTHONPATH=.:$$PYTHONPATH mypy nvpy tests benchmarks debug-utils
	PYTHONPATH=.:$$PYTHONPATH coverage run -m unittest discover -s tests -p '*.py'
	# Generate coverage report.
	coverage report --skip-covered nvpy/*.py
	coverage html
	# Open htmlcov/index.html in a Web browser.

.PHONY: benchmark
benchmark:
	PYTHONPATH=.:$$PYTHONPATH python3 benchmarks/sorters.py
	PYTHONPATH=.:$$PYTHONPATH python3 benchmarks/notes_list.py

.PHONY: docs
docs:
	python3 -m pdoc --http localhost:8080 nvpy
