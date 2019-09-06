
test:
	PYTHONPATH=.:$$PYTHONPATH python3 -m unittest discover -s tests -p '*.py'
