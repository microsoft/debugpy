PYTHON ?= python3


.PHONY: help
help:  ## Print help about available targets.
	@grep -h -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.PHONY: depends
depends:
	$(PYTHON) -m pip install setuptools
	$(PYTHON) -m pip install flake8
	$(PYTHON) -m pip install coverage

.PHONY: lint
lint:
	#$(PYTHON) -m flake8 --ignore E24,E121,E123,E125,E126,E221,E226,E266,E704,E265,E501 --exclude ptvsd/pydevd $(CURDIR)
	$(PYTHON) -m tests --lint-only

.PHONY: test
test:  ## Run the test suite.
	$(PYTHON) -m tests --full

.PHONY: test-quick
test-quick:
	$(PYTHON) -m tests --quick

.PHONY: ci-test
ci-test:
	$(PYTHON) -m tests --full --no-network

.PHONY: check-dap-schema
check-dap-schema:
	$(PYTHON) -m debugger_protocol.schema check

.PHONY: coverage
coverage:  ## Check line coverage.
	#$(PYTHON) -m coverage run --include 'ptvsd/*.py' --omit 'ptvsd/pydevd/*.py' -m tests
	$(PYTHON) -m tests --full --coverage

.PHONY: ci-coverage
ci-coverage:
	$(PYTHON) -m tests --full --coverage --no-network

.PHONY: check-schemafile
check-schemafile:  ## Validate the vendored schema file.
	python3 -m debugger_protocol.schema check
