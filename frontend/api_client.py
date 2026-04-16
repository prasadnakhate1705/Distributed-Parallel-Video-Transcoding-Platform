"""Thin wrapper around requests that injects the API key header on every call."""
import requests
from frontend.config import FLASK_URL, API_KEY

_HEADERS = {"X-API-Key": API_KEY}


def get(path: str, **kwargs) -> requests.Response:
    return requests.get(f"{FLASK_URL}{path}", headers=_HEADERS, **kwargs)


def post(path: str, **kwargs) -> requests.Response:
    # Merge caller-supplied headers with auth header
    caller_headers = kwargs.pop("headers", {})
    return requests.post(
        f"{FLASK_URL}{path}",
        headers={**_HEADERS, **caller_headers},
        **kwargs,
    )
