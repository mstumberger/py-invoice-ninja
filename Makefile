.PHONY: test coverage lint clean

test:
	python3 -m unittest

coverage:
	python3 -m coverage run -m unittest
	python3 -m coverage report -m

lint:
	python3 -m pyflakes invoice_ninja tests || true

clean:
	rm -rf build dist *.egg-info .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
