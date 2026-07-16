---
description: Best practices for developing Python code in this repository
applyTo: '**/*.py'
---

# Python Best Practices

## Section 1: Universal Rules

Non-negotiable. Always follow these regardless of project tooling or configuration.

### 1.1 Put All Tests in a `tests/` Directory

Never scatter test files at the top level alongside source code. Place all tests in a dedicated `tests/` subdirectory. If using pytest, configure test path discovery in `pyproject.toml`.

```
# Correct
my_project/
  src/app.py
  src/utils.py
  tests/test_app.py
  tests/test_utils.py
```

### 1.2 Use the Simplest Build Tool That Works

For pure Python projects, prefer modern build backends like hatchling or pdm-backend. Do not default to setuptools unless the project already uses it.

### 1.3 Never Write Dependencies in Multiple Places

Define direct dependencies in one place only (`pyproject.toml`). Do not duplicate them across `requirements.txt`, `pyproject.toml`, and `setup.py`.

### 1.4 Dev Dependencies Go in `[dependency-groups]`

Development dependencies (pytest, ruff, mypy) belong in `[dependency-groups] dev`, not `[project.optional-dependencies]`.

### 1.5 Use Leading Underscores for Non-Public APIs

Add leading underscores to modules, classes, functions, and methods that are not part of the public API.

### 1.6 Imports Belong at the Top of the File

Place all imports at the top of the file. Inline imports should only be used for lazy loading or circular import resolution.

### 1.7 Follow PEP 8 Naming Conventions

- `snake_case` for functions and variables
- `PascalCase` for classes
- `UPPER_SNAKE_CASE` for constants
- `_leading_underscore` for private/internal names

### 1.8 Write Idiomatic Python for the Target Version

Use features available in the project's target Python version. Use `match`/`case`, type union syntax (`X | Y`), `pathlib`, and built-in generics where supported.

### 1.9 Avoid Deep Nesting — Use Early Returns

Avoid nesting code deeper than 3 levels. Use guard clauses, early returns, `continue` in loops, and extracted helper functions to flatten logic.

### 1.10 Default to Fail-Closed Logic

For authorization and security checks, structure code to fail-closed (deny by default).

### 1.11 Prefer Built-ins and Comprehensions Over Helper Methods

Use `any()`, `all()`, `sum()`, `min()`, `max()` and other built-ins. Leverage comprehensions and generators.

### 1.12 Match the Project's Existing Test Framework

Default to pytest unless preexisting code uses unittest. Respect existing patterns.

### 1.13 Don't Over-Mock in Tests

Mock external dependencies (APIs, databases) but test actual business logic with real objects when possible.

### 1.14 Don't Over-Document — Explain Why, Not What

Comments should explain why, not what. Code should be self-documenting through clear naming.

### 1.15 Write Library-Quality Code, Not Scripts

Structure code as a library or reusable software product. Use proper classes, modules, error handling, and separation of concerns.

## Section 2: Environment-Aware Guidance

These rules adapt based on detected project conventions. Framework-specific skills extend this section.

### 2.1 Formatter and Linter

If a project configuration is detected (e.g. `ruff.toml`, `pyproject.toml [tool.ruff]`, `.flake8`), follow the project's formatter/linter. If none is detected, prefer Ruff for both formatting and linting.

### 2.2 Source Layout

Respect the detected source layout (`src/` layout vs flat package). If creating a new project, prefer the `src/` layout.

### 2.3 Test Framework

Detect and follow the existing test framework. If no existing framework is detected, default to pytest.
