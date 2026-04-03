---
name: django
description: Best practices for Django web development including models, views, templates, and testing.
---

# Skill: Django

Best practices for Django web development including models, views, templates, and testing.

## When to Use

Apply this skill when working with Django projects — models, views, URL routing, templates, forms, admin, and management commands.

## Project Structure

-   Follow the standard Django app layout: `models.py`, `views.py`, `urls.py`, `admin.py`, `tests.py`, `forms.py`.
-   Keep each app focused on a single domain concept; avoid "god apps" with unrelated models.
-   Use `settings/base.py`, `settings/dev.py`, `settings/prod.py` for environment-specific configuration.

## Models

-   Always define `__str__` on models for admin and debugging readability.
-   Use `Meta.ordering` sparingly — it adds `ORDER BY` to every query. Prefer explicit `.order_by()` on querysets.
-   Use database indexes (`db_index=True`, `Meta.indexes`) for fields that appear in `filter()` / `order_by()`.
-   Prefer `CharField` with `choices` (or `TextChoices` / `IntegerChoices`) over bare strings for constrained fields.
-   Use `F()` expressions and `Q()` objects for complex queries to avoid race conditions and improve readability.

## Views

-   Prefer class-based views (CBVs) for CRUD; prefer function-based views for one-off logic.
-   Always explicitly set `queryset` or override `get_queryset()` — never rely on mutable class-level state.
-   Use `select_related()` and `prefetch_related()` to avoid N+1 query problems.
-   Set `LOGIN_URL` and use `@login_required` / `LoginRequiredMixin` consistently.

## Testing

-   Use `pytest-django` with `@pytest.mark.django_db` for database access.
-   Prefer `TestCase` or `TransactionTestCase` only when explicit transaction control is needed; otherwise use pytest fixtures.
-   Use `RequestFactory` or `Client` to test views without starting a server.
-   Use `baker.make()` (model-bakery) or factories instead of manual model construction in tests.

## Pitfalls

-   Never do blocking I/O in async views without wrapping in `sync_to_async`.
-   Avoid importing models at module level in `settings.py` or `urls.py` (circular imports).
-   Never store secrets in `settings.py` — use environment variables.
-   Avoid raw SQL unless the ORM genuinely cannot express the query.
