.PHONY: all
all: format test

.PHONY: format
format:
	yapf -r -p -i .

.PHONY: test
test:
	PYTHONPATH=.:$$PYTHONPATH python3 -m unittest discover -s tests -p '*.py'
