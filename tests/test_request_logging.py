from __future__ import annotations

from starlette.requests import Request

from server.app import _request_log_source


def _request(headers: list[tuple[bytes, bytes]], client_host: str = "10.0.0.2") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/projects/missing/events/stream",
            "headers": headers,
            "client": (client_host, 54321),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


def test_request_log_source_uses_forwarded_for_and_user_agent() -> None:
    request = _request(
        [
            (b"x-forwarded-for", b"203.0.113.10, 10.0.0.5"),
            (b"user-agent", b"Mozilla/5.0"),
        ],
        client_host="172.18.0.1",
    )

    assert _request_log_source(request) == 'client=203.0.113.10 ua="Mozilla/5.0"'


def test_request_log_source_falls_back_to_socket_client_and_sanitizes_user_agent() -> None:
    request = _request([(b"user-agent", b"Bad\r\nAgent\tName")], client_host="127.0.0.1")

    assert _request_log_source(request) == 'client=127.0.0.1 ua="Bad Agent Name"'
