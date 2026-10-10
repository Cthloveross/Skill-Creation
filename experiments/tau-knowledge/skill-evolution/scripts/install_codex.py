#!/usr/bin/env python3
"""Install the two pinned native Codex binaries without root or a handoff ZIP."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import tarfile
import tempfile
import urllib.request
from pathlib import Path

VERSION = "0.160.1"
RELEASE = f"https://github.com/openai/codex/releases/download/rust-v{VERSION}"
# Release archive digests and the extracted binaries are checked independently.
ASSETS = (
    {
        "name": "codex",
        "member": "codex-x86_64-unknown-linux-musl",
        "archive_sha256": "9226581be592d18f7e7f740a352fdb63aa61e45e39f7eb9b09d3888c84bba33f",
        "binary_sha256": "f34a4d2301892ae96c90097786bfe5dc269f187b6f69faf42a7b357b8c081e35",
    },
    {
        "name": "codex-code-mode-host",
        "member": "codex-code-mode-host-x86_64-unknown-linux-musl",
        "archive_sha256": "8a69207d97545ac753b6585974e1e67a4c51ae5deacf06517db512bb25e0e3c2",
        "binary_sha256": "b33e8a5283f3c65c2a0aca6d43a59cfe850f624d8fa16992e3cad4fcc27c14e1",
    },
)
MAX_ARCHIVE_BYTES = 160 * 1024 * 1024
MAX_BINARY_BYTES = 384 * 1024 * 1024
PROJECT = Path(__file__).resolve().parents[4]


def _hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _valid_install(destination: Path, assets: tuple[dict, ...]) -> bool:
    return all(
        (path := destination / asset["name"]).is_file()
        and not path.is_symlink()
        and os.access(path, os.X_OK)
        and _hash(path) == asset["binary_sha256"]
        for asset in assets
    )


def _download_binary(asset: dict, staging: Path) -> None:
    archive = staging / f"{asset['name']}.tar.gz"
    request = urllib.request.Request(
        f"{RELEASE}/{asset['member']}.tar.gz", headers={"User-Agent": "SkillsBench-bootstrap"}
    )
    size = 0
    with urllib.request.urlopen(request, timeout=60) as response, archive.open("xb") as output:
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_ARCHIVE_BYTES:
                raise ValueError("Codex release archive exceeds size limit")
            output.write(chunk)
    if _hash(archive) != asset["archive_sha256"]:
        raise ValueError(f"Codex archive hash mismatch: {asset['name']}")
    # Do not extract archive paths. Only copy the expected regular-file member.
    with tarfile.open(archive, "r:gz") as package:
        member = package.next()
        if (
            member is None
            or member.name != asset["member"]
            or not member.isfile()
            or not 0 < member.size <= MAX_BINARY_BYTES
        ):
            raise ValueError(f"Unsafe Codex release archive: {asset['name']}")
        with package.extractfile(member) as source, (staging / asset["name"]).open("xb") as output:
            remaining = member.size
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError("Truncated Codex binary")
                output.write(chunk)
                remaining -= len(chunk)
        if package.next() is not None:
            raise ValueError("Unexpected additional Codex archive member")
    binary = staging / asset["name"]
    if _hash(binary) != asset["binary_sha256"]:
        raise ValueError(f"Codex binary hash mismatch: {asset['name']}")
    binary.chmod(0o755)
    archive.unlink()


def install(destination: Path, assets: tuple[dict, ...] = ASSETS) -> str:
    destination = destination.absolute()
    if destination.is_symlink():
        raise ValueError("Codex destination must not be a symlink")
    if destination.exists():
        if destination.is_dir() and _valid_install(destination, assets):
            return "already_installed"
        raise ValueError(f"Invalid existing Codex installation; remove it first: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".codex-install-", dir=destination.parent) as temporary:
        staging = Path(temporary) / "bin"
        staging.mkdir()
        for asset in assets:
            _download_binary(asset, staging)
        # Publish only after both binaries pass their pinned hashes.
        staging.rename(destination)
    return "installed"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--destination", type=Path, default=PROJECT / "data" / "tools" / f"codex-{VERSION}"
    )
    args = parser.parse_args()
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "AMD64"}:
        parser.error("The pinned runtime requires Linux x86_64")
    try:
        status = install(args.destination)
    except (OSError, ValueError, tarfile.TarError) as error:
        parser.exit(1, f"Codex installation failed: {error}\n")
    print(json.dumps({"status": status, "version": VERSION, "directory": str(args.destination)}))


if __name__ == "__main__":
    main()
