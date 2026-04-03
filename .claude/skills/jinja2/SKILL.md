---
name: jinja2
description: Best practices for template rendering with Jinja2 including environments, filters, autoescaping, and security.
---

# Skill: Jinja2

Best practices for template rendering with Jinja2 including environments, filters, autoescaping, and security.

## When to Use

Apply this skill when rendering templates with Jinja2 — HTML pages, emails, configuration files, and code generation.

## Environment

-   Create a `jinja2.Environment(loader=..., autoescape=...)` once and reuse it.
-   Use `FileSystemLoader` for file-based templates, `PackageLoader` for installed packages.
-   Enable `autoescape=True` for HTML templates to prevent XSS.

## Templates

-   Use `{{ variable }}` for output, `{% if/for/block %}` for control flow.
-   Use template inheritance (`{% extends 'base.html' %}`) for layout reuse.
-   Define custom filters for reusable transformations.

## Security

-   **Always** enable `autoescape=True` when rendering HTML.
-   Use `SandboxedEnvironment` for untrusted templates.
-   Never render user input as template code — only as template data.
-   Use `|e` filter explicitly when autoescape is off.

## Pitfalls

-   Don't use `Template(string)` directly — it bypasses the environment's loader and settings.
-   Watch for undefined variable errors — use `undefined=StrictUndefined` during development.
-   Avoid complex logic in templates — keep them focused on presentation.
