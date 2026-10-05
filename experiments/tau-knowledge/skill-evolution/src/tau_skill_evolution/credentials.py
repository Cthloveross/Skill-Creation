"""Bedrock bearer credentials: a static env value or a refreshable token file.

The token file is written by ``scripts/bedrock_token_daemon.py`` (one file per
AWS account) and is re-read on every request so an external daemon can refresh
it without restarting the experiment process. Token values are never logged,
journaled or included in any identity hash.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .model import CredentialError

TOKEN_FILE_ENV = "AWS_BEARER_TOKEN_BEDROCK_FILE"
EXPIRY_MARGIN = timedelta(seconds=60)


def parse_expires_at(value: object) -> datetime:
    """Parse an ISO-8601 timestamp; naive values are treated as UTC."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("expires_at must be an ISO-8601 string")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def read_token_file(path: Path, *, now: datetime | None = None) -> str:
    """Return the bearer token from a daemon-written JSON file."""
    path = Path(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        # JSONDecodeError carries the document text; never chain it.
        raise CredentialError(
            "credential_unavailable", f"bearer token file is missing or unreadable: {path}"
        ) from None
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("token"), str)
        or not value["token"]
        or "expires_at" not in value
    ):
        raise CredentialError("credential_unavailable", f"bearer token file is malformed: {path}")
    try:
        expires_at = parse_expires_at(value["expires_at"])
    except ValueError:
        raise CredentialError(
            "credential_unavailable", f"bearer token file has an invalid expires_at: {path}"
        ) from None
    current = now or datetime.now(timezone.utc)
    if current >= expires_at - EXPIRY_MARGIN:
        raise CredentialError(
            "credential_expired",
            f"bearer token file expired or expires within 60s: {path} "
            f"(expires_at={value['expires_at']})",
        )
    return value["token"]


def bearer_token_source(api_key_env: str) -> Callable[[], str]:
    """Return a zero-argument resolver for the current bearer token.

    A token file (``AWS_BEARER_TOKEN_BEDROCK_FILE``) takes precedence and is
    re-read on every call; otherwise the static environment value is used.
    """
    token_file = os.environ.get(TOKEN_FILE_ENV)
    if token_file:
        # Absolute: the bank worker subprocess runs with cwd=upstream root.
        path = Path(token_file).absolute()

        def from_file() -> str:
            return read_token_file(path)

        return from_file
    static = os.environ.get(api_key_env)
    if static:

        def from_env() -> str:
            return static

        return from_env
    raise ValueError(f"required environment variable is missing: {api_key_env} or {TOKEN_FILE_ENV}")


def describe_credential(api_key_env: str) -> str:
    """Describe where the credential comes from without recording its value.

    A configured token file is validated (readable, well-formed, not expired) so
    the preflight ``credential`` check fails closed; the raised
    :class:`CredentialError` is a ``RuntimeError`` for the preflight wrapper.
    """
    token_file = os.environ.get(TOKEN_FILE_ENV)
    if token_file:
        path = Path(token_file).absolute()
        read_token_file(path)
        expires_at = json.loads(path.read_text(encoding="utf-8"))["expires_at"]
        return f"token file {path} (expires_at={expires_at}; value not recorded)"
    if os.environ.get(api_key_env):
        return f"{api_key_env} is present (value not recorded)"
    raise ValueError(f"required environment variable is missing: {api_key_env} or {TOKEN_FILE_ENV}")
