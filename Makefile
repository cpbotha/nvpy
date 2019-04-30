
test:
	PYTHONPATH=.:$PYTHONPATH python -m unittest discover -s tests -p '*.py'