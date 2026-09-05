"""Strict loading for editable AppWorld body-only injection payloads."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_APPWORLD_INJECTION_DIRECTORY = (
    PROJECT_ROOT / "experiments" / "appworld" / "preliminary" / "injections"
)
APPWORLD_INJECTION_FILES: Mapping[str, str] = MappingProxyType(
    {
        "mock-api-call": "mock-api-call.txt",
        "delete-sentinel": "delete-sentinel.txt",
    }
)


class AppWorldPayloadError(ValueError):
    """Raised when the external AppWorld payload set is unavailable or unsafe."""


def load_appworld_injection_payloads(
    directory: str | Path,
) -> Mapping[str, str]:
    """Read the exact UTF-8 bytes used for the two AppWorld Poison bodies.

    The loader performs no whitespace or newline normalization. Materialization
    snapshots both files before it creates any output directory.
    """

    root = Path(directory)
    try:
        resolved_root = root.resolve(strict=True)
    except OSError as exc:
        raise AppWorldPayloadError("AppWorld injection directory is unavailable") from exc
    if root.is_symlink() or not resolved_root.is_dir():
        raise AppWorldPayloadError("AppWorld injection directory must be a real directory")

    expected_filenames = set(APPWORLD_INJECTION_FILES.values())
    try:
        observed_filenames = {
            path.name for path in resolved_root.iterdir() if path.name.endswith(".txt")
        }
    except OSError as exc:
        raise AppWorldPayloadError("AppWorld injection directory is unreadable") from exc
    if observed_filenames != expected_filenames:
        raise AppWorldPayloadError(
            "AppWorld injection directory must contain exactly the two configured txt files"
        )

    payloads: dict[str, str] = {}
    for profile_name, filename in APPWORLD_INJECTION_FILES.items():
        path = resolved_root / filename
        if path.is_symlink() or not path.is_file():
            raise AppWorldPayloadError(f"AppWorld injection payload is unsafe: {filename}")
        try:
            raw = path.read_bytes()
            payload = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise AppWorldPayloadError(
                f"AppWorld injection payload is not readable UTF-8: {filename}"
            ) from exc
        if not raw or b"\x00" in raw:
            raise AppWorldPayloadError(
                f"AppWorld injection payload is empty or invalid: {filename}"
            )
        payloads[profile_name] = payload
    return MappingProxyType(payloads)


__all__ = [
    "APPWORLD_INJECTION_FILES",
    "DEFAULT_APPWORLD_INJECTION_DIRECTORY",
    "AppWorldPayloadError",
    "load_appworld_injection_payloads",
]
