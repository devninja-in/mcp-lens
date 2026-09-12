from __future__ import annotations

import re
from typing import Any

_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|apikey)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(bearer\s+)\S+"),
    re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(secret|token)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(authorization)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(cookie)\s*[:=]\s*\S+"),
]

_SECRET_KEY_NAMES = {
    "api_key",
    "apikey",
    "api-key",
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "auth_token",
    "bearer",
    "cookie",
    "session_id",
    "credentials",
    "private_key",
    "client_secret",
}

_REDACTED = "***REDACTED***"


def redact_secrets(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: _redact_value(k, v) for k, v in data.items()}
    if isinstance(data, list):
        return [redact_secrets(item) for item in data]
    if isinstance(data, str):
        return _redact_string(data)
    return data


def _redact_value(key: str, value: Any) -> Any:
    if isinstance(key, str) and key.lower() in _SECRET_KEY_NAMES and isinstance(value, str) and value:
        return _REDACTED
    return redact_secrets(value)


def _redact_string(s: str) -> str:
    result = s
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub(lambda m: m.group(1) + _REDACTED, result)
    return result
