---
name: flask
description: Best practices for Flask web development including routing, blueprints, and testing.
---

# Skill: Flask

Best practices for Flask web development including routing, blueprints, and testing.

## When to Use

Apply this skill when building Flask web applications or APIs — routing, blueprints, extensions, and testing.

## Project Structure

-   Use the application factory pattern (`create_app()`) to avoid global state and enable testing.
-   Organize features into Blueprints; register them in the factory.
-   Keep configuration in a `config.py` with classes like `DevelopmentConfig`, `ProductionConfig`.

## Routing and Views

-   Prefer explicit HTTP method decorators (`@app.get`, `@app.post`) over generic `@app.route` with `methods=[...]`.
-   Validate request data early; return 400 errors for malformed input before processing.
-   Use `flask.abort()` with appropriate HTTP codes rather than returning error responses manually.

## Extensions

-   Initialize extensions lazily with `ext.init_app(app)` inside the factory, not at module level.
-   Common extensions: Flask-SQLAlchemy, Flask-Migrate, Flask-Login, Flask-WTF, Flask-CORS.

## Testing

-   Use `app.test_client()` for HTTP-level tests and `app.test_request_context()` for unit tests.
-   Use pytest fixtures to create the app and client; scope appropriately (`session` for the app, `function` for the client).
-   Set `TESTING=True` and use a separate test database.

## Pitfalls

-   Never use the development server (`app.run()`) in production — use Gunicorn or uWSGI.
-   Avoid storing mutable state on the `app` object; use `g` for request-scoped data.
-   Never hardcode `SECRET_KEY` — load from environment variables.
