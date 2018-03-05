PYTHON ?= python3

.PHONY: help
help:  ## Print help about available targets.
	@grep -h -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.PHONY: depends
depends:
	$(PYTHON) -m pip install flake8
	$(PYTHON) -m pip install coverage

.PHONY: lint
lint:
	$(PYTHON) -m tests --lint-only

.PHONY: test
test:  ## Run the test suite.
	$(PYTHON) -m tests --full

.PHONY: test-quick
test-quick:
	$(PYTHON) -m tests --quick

.PHONY: coverage
coverage:  ## Check line coverage.
	$(PYTHON) -m coverage run --include 'ptvsd/*.py' --omit 'ptvsd/pydevd/*.py' -m tests

.PHONY: check-schemafile
check-schemafile:  ## Validate the vendored schema file.
	python3 -m debugger_protocol.schema check
