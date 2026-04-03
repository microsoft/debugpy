---
name: pytest
description: Best practices for writing and organizing tests with pytest including fixtures, parametrize, and plugins.
---

# Skill: pytest

Best practices for writing and organizing tests with pytest including fixtures, parametrize, and plugins.

## When to Use

Apply this skill when writing and organizing tests with pytest — fixtures, parametrize, markers, plugins, and test structure.

## Test Organization

-   Place tests in a `tests/` directory mirroring the source structure.
-   Name test files `test_<module>.py` and test functions `test_<behavior>()`.
-   Group related tests in classes only when they share fixtures/setup.

## Fixtures

-   Define fixtures at the narrowest scope needed (`function` > `class` > `module` > `session`).
-   Use `conftest.py` for shared fixtures; put it at the appropriate directory level.
-   Prefer factory fixtures over complex fixture inheritance.
-   Use `yield` fixtures for setup/teardown; prefer `tmp_path` over `tempfile`.

## Parametrize

-   Use `@pytest.mark.parametrize` for data-driven tests with multiple inputs.
-   Give test IDs (`ids=...`) for readable test output.
-   Combine `parametrize` with fixtures for cross-product testing.

## Assertions

-   Use plain `assert` statements — pytest rewrites them for clear failure messages.
-   Use `pytest.raises(ExceptionType, match=...)` for exception testing.
-   Use `pytest.approx()` for floating-point comparisons.

## Plugins

-   Common plugins: `pytest-cov`, `pytest-mock`, `pytest-asyncio`, `pytest-xdist`, `pytest-timeout`.
-   Use `pytest-mock`'s `mocker` fixture over raw `unittest.mock.patch`.

## Pitfalls

-   Don't use `session`-scoped fixtures for mutable state.
-   Don't assert on implementation details — test observable behavior.
-   Avoid test interdependence; each test should be runnable in isolation.

