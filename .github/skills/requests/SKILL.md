---
name: requests
description: Best practices for HTTP client usage with Requests including sessions, error handling, and timeouts.
---

# Skill: Requests

Best practices for HTTP client usage with Requests including sessions, error handling, and timeouts.

## When to Use

Apply this skill when making HTTP requests with the Requests library — sessions, auth, error handling, retries, and file uploads.

## Sessions

-   Use `requests.Session()` for connection pooling and persistent headers/cookies across multiple requests.
-   Configure `session.headers` for default auth tokens and user-agent strings.
-   Use `session.mount()` with `HTTPAdapter` for retry logic.

## Error Handling

-   Always call `response.raise_for_status()` to surface HTTP errors as exceptions.
-   Always set `timeout=(connect_timeout, read_timeout)` — never use infinite timeouts.
-   Handle `requests.ConnectionError`, `requests.Timeout`, and `requests.HTTPError` explicitly.

## Retries

-   Use `urllib3.util.Retry` with `HTTPAdapter` for automatic retries with backoff.
-   Configure status-based retries for transient errors (429, 500, 502, 503, 504).

## Security

-   Never disable SSL verification (`verify=False`) in production.
-   Pass credentials via environment variables, not hardcoded strings.
-   Use `auth=` parameter for HTTP auth rather than manually setting headers.

## Pitfalls

-   Don't forget timeouts — they default to None (infinite wait).
-   Don't use `requests.get()` for high-throughput — use sessions.
-   Close responses from streaming requests (`stream=True`) to release connections.

