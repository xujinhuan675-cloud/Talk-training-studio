from __future__ import annotations

from api.middleware.logging import LoggingMiddleware


async def _noop_app(scope, receive, send):
    return None


def test_logging_middleware_sanitizes_query_and_nested_secret_fields() -> None:
    middleware = LoggingMiddleware(_noop_app)

    sanitized = middleware._sanitize_data(
        {
            "newapi_token": "query-token",
            "from": "/practice",
            "nested": {
                "client_secret": "secret-value",
                "token_count": 12,
            },
        }
    )

    assert sanitized == {
        "newapi_token": "***",
        "from": "/practice",
        "nested": {
            "client_secret": "***",
            "token_count": 12,
        },
    }


def test_logging_middleware_sanitizes_referer_query_and_hash_tokens() -> None:
    middleware = LoggingMiddleware(_noop_app)

    referer = middleware._sanitize_url(
        "https://talkwise.example/login?from=%2Fpractice&talkwise_code=handoff"
        "#/return?access_token=hash-token&next=%2Freview"
    )

    assert referer == (
        "https://talkwise.example/login?from=%2Fpractice&talkwise_code=***"
        "#/return?access_token=***&next=%2Freview"
    )
