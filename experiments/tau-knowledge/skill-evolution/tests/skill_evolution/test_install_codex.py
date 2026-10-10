"""Offline release fixtures for the project-local pinned Codex installer."""

import hashlib
import importlib.util
import io
import tarfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "install_codex.py"
SPEC = importlib.util.spec_from_file_location("install_codex", SCRIPT)
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


def _archive(name, content=b"native-binary", *, kind=tarfile.REGTYPE, extra=False):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as package:
        member = tarfile.TarInfo(name)
        member.type = kind
        member.linkname = "/outside"
        member.size = len(content) if kind == tarfile.REGTYPE else 0
        package.addfile(member, io.BytesIO(content))
        if extra:
            package.addfile(tarfile.TarInfo("unexpected"), io.BytesIO())
    return stream.getvalue()


def _asset(name="codex", content=b"native-binary", archive=None):
    member = f"{name}-x86_64-unknown-linux-musl"
    archive = _archive(member, content) if archive is None else archive
    return {
        "name": name,
        "member": member,
        "archive_sha256": hashlib.sha256(archive).hexdigest(),
        "binary_sha256": hashlib.sha256(content).hexdigest(),
    }, archive


def _serve(monkeypatch, downloads):
    calls = []

    def urlopen(request, timeout):
        calls.append((request.full_url, timeout))
        return io.BytesIO(downloads[len(calls) - 1])

    monkeypatch.setattr(installer.urllib.request, "urlopen", urlopen)
    return calls


def test_install_downloads_only_two_pinned_assets_and_is_idempotent(tmp_path, monkeypatch):
    codex, first = _asset()
    companion, second = _asset("codex-code-mode-host", b"companion-binary")
    calls = _serve(monkeypatch, [first, second])
    destination = tmp_path / "tools" / "codex-0.160.1"
    assert installer.install(destination, (codex, companion)) == "installed"
    assert sorted(path.name for path in destination.iterdir()) == ["codex", "codex-code-mode-host"]
    assert installer.install(destination, (codex, companion)) == "already_installed"
    assert calls == [
        (f"{installer.RELEASE}/{codex['member']}.tar.gz", 60),
        (f"{installer.RELEASE}/{companion['member']}.tar.gz", 60),
    ]
    assert (destination / "codex").stat().st_mode & 0o777 == 0o755
    assert not list(destination.parent.glob(".codex-install-*"))


@pytest.mark.parametrize("field", ["archive_sha256", "binary_sha256"])
def test_hash_mismatch_does_not_publish_partial_install(tmp_path, monkeypatch, field):
    asset, archive = _asset()
    asset[field] = "0" * 64
    _serve(monkeypatch, [archive])
    destination = tmp_path / "codex"
    with pytest.raises(ValueError, match="hash mismatch"):
        installer.install(destination, (asset,))
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("name", "kind", "extra"),
    [
        ("../../escape", tarfile.REGTYPE, False),
        ("/absolute", tarfile.REGTYPE, False),
        ("codex-x86_64-unknown-linux-musl", tarfile.SYMTYPE, False),
        ("codex-x86_64-unknown-linux-musl", tarfile.LNKTYPE, False),
        ("codex-x86_64-unknown-linux-musl", tarfile.REGTYPE, True),
    ],
)
def test_unsafe_tar_members_are_rejected(tmp_path, monkeypatch, name, kind, extra):
    asset, archive = _asset(archive=_archive(name, kind=kind, extra=extra))
    _serve(monkeypatch, [archive])
    with pytest.raises(ValueError, match="archive"):
        installer.install(tmp_path / "codex", (asset,))
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("limit", ["MAX_ARCHIVE_BYTES", "MAX_BINARY_BYTES"])
def test_download_and_extraction_size_limits(tmp_path, monkeypatch, limit):
    asset, archive = _asset()
    _serve(monkeypatch, [archive])
    monkeypatch.setattr(installer, limit, 1)
    with pytest.raises(ValueError, match="size limit|Unsafe"):
        installer.install(tmp_path / "codex", (asset,))
    assert not list(tmp_path.iterdir())


def test_second_download_failure_keeps_destination_absent(tmp_path, monkeypatch):
    codex, first = _asset()
    companion, second = _asset("codex-code-mode-host")
    companion["binary_sha256"] = "0" * 64
    _serve(monkeypatch, [first, second])
    with pytest.raises(ValueError, match="hash mismatch"):
        installer.install(tmp_path / "codex", (codex, companion))
    assert not list(tmp_path.iterdir())


def test_existing_invalid_or_symlink_destination_is_not_overwritten(tmp_path, monkeypatch):
    calls = _serve(monkeypatch, [])
    destination = tmp_path / "codex"
    destination.mkdir()
    (destination / "codex").write_text("corrupt")
    with pytest.raises(ValueError, match="Invalid existing"):
        installer.install(destination)
    assert (destination / "codex").read_text() == "corrupt"
    linked = tmp_path / "linked"
    linked.symlink_to(destination, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        installer.install(linked)
    assert not calls
