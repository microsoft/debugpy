PYTHON ?= python3


.PHONY: help
help:  ## Print help about available targets.
	@grep -h -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.PHONY: depends
depends:
	$(PYTHON) -m pip install setuptools
	$(PYTHON) -m pip install flake8
	$(PYTHON) -m pip install flake8_formatter_junit_xml
	$(PYTHON) -m pip install unittest-xml-reporting
	$(PYTHON) -m pip install coverage
	$(PYTHON) -m pip install requests
	$(PYTHON) -m pip install flask
	$(PYTHON) -m pip install django
	$(PYTHON) -m pip install pytest

.PHONY: lint
lint:  ## Lint the Python source code.
	#$(PYTHON) -m flake8 --ignore E24,E121,E123,E125,E126,E221,E226,E266,E704,E265,E501 --exclude ptvsd/pydevd $(CURDIR)
	$(PYTHON) -m tests --lint-only

.PHONY: test
test:  ## Run the test suite.
	$(PYTHON) -m tests -v --full

.PHONY: test-quick
test-quick:
	$(PYTHON) -m tests -v --quick

.PHONY: coverage
coverage:  ## Check line coverage.
	#$(PYTHON) -m coverage run --include 'ptvsd/*.py' --omit 'ptvsd/pydevd/*.py' -m tests
	$(PYTHON) -m tests -v --full --coverage

.PHONY: check-schemafile
check-schemafile:  ## Validate the vendored DAP schema file.
	$(PYTHON) -m debugger_protocol.schema check


##################################
# CI

.PHONY: ci-lint
ci-lint: depends lint

.PHONY: ci-test
ci-test: depends
	# For now we use --quickpy2.
	$(PYTHON) -m tests -v --full --no-network --quick-py2
	$(PYTHON) setup.py test

.PHONY: ci-coverage
ci-coverage: depends
	$(PYTHON) -m tests -v --full --coverage --no-network

.PHONY: ci-check-schemafile
ci-check-schemafile: check-schemafile
