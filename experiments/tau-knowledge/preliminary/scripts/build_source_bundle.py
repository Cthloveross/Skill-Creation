#!/usr/bin/env python3
"""Build a deterministic, auditable bundle of the current source worktree.

The command is dry-run by default. Pass ``--write`` to persist the bundle.
Ignored files, Git internals, archives, model weights, caches, prior runs,
materialized corpora, and unrelated untracked experiment assets are excluded.
The remaining inventory comes from ``git ls-files``.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from getpass import getuser
from pathlib import Path, PurePosixPath

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
BUNDLE_PREFIX = "Skill-Creation"
MANIFEST_NAME = "SOURCE_BUNDLE_MANIFEST.json"
EXCLUDED_DIRECTORY_NAMES = frozenset(
    {
        ".cache",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "materialized",
        "runs",
    }
)
EXCLUDED_FILE_SUFFIXES = (
    ".bin",
    ".log",
    ".pt",
    ".pyc",
    ".safetensors",
    ".sif",
    ".tar",
    ".tar.gz",
    ".tgz",
    ".zip",
)
# Untracked source, configuration, and tests are part of the current worktree.
# The generated-path exclusions and Git ignore rules exclude runtime assets.
IRRELEVANT_UNTRACKED_GLOBS: tuple[str, ...] = ()


class BundleError(RuntimeError):
    """Raised when the source inventory cannot be frozen safely."""


@dataclass(frozen=True)
class SourceFile:
    relative_path: str
    data: bytes
    mode: int

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


def _git(root: Path, *arguments: str) -> bytes:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), *arguments],
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="replace").strip()
        raise BundleError(f"git {' '.join(arguments)} failed: {detail}") from exc


def _decode_paths(raw: bytes) -> tuple[str, ...]:
    return tuple(item.decode("utf-8") for item in raw.split(b"\0") if item)


def _excluded_generated_path(relative: str) -> bool:
    path = PurePosixPath(relative)
    return bool(EXCLUDED_DIRECTORY_NAMES.intersection(path.parts)) or path.name.endswith(
        EXCLUDED_FILE_SUFFIXES
    )


def _excluded_untracked_path(relative: str) -> bool:
    return _excluded_generated_path(relative) or any(
        fnmatch.fnmatchcase(relative, pattern) for pattern in IRRELEVANT_UNTRACKED_GLOBS
    )


def _listed_paths(root: Path) -> tuple[str, ...]:
    tracked = _decode_paths(_git(root, "ls-files", "-z", "--cached"))
    deleted = set(_decode_paths(_git(root, "ls-files", "-z", "--deleted")))
    untracked = _decode_paths(_git(root, "ls-files", "-z", "--others", "--exclude-standard"))
    paths = tuple(
        sorted(
            {
                *(
                    relative
                    for relative in tracked
                    if relative not in deleted and not _excluded_generated_path(relative)
                ),
                *(relative for relative in untracked if not _excluded_untracked_path(relative)),
            }
        )
    )
    if not paths:
        raise BundleError("Git returned an empty source inventory")
    if len(paths) != len(set(paths)):
        raise BundleError("Git returned duplicate source paths")
    return paths


def _validate_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise BundleError(f"unsafe source path: {value!r}")
    if path.parts[0] == ".git":
        raise BundleError("refusing to bundle Git internals")
    return path


def _read_sources(root: Path) -> tuple[SourceFile, ...]:
    listed_before = _listed_paths(root)
    sources: list[SourceFile] = []
    for relative in listed_before:
        _validate_relative_path(relative)
        path = root / relative
        if path.is_symlink():
            raise BundleError(f"symbolic links are not allowed in the source bundle: {relative}")
        if not path.is_file():
            raise BundleError(f"source path is not a regular file: {relative}")
        before = path.stat()
        data = path.read_bytes()
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise BundleError(f"source file changed while it was read: {relative}")
        mode = 0o755 if before.st_mode & stat.S_IXUSR else 0o644
        sources.append(SourceFile(relative_path=relative, data=data, mode=mode))

    if _listed_paths(root) != listed_before:
        raise BundleError("source inventory changed while the bundle was prepared")
    for source in sources:
        if hashlib.sha256((root / source.relative_path).read_bytes()).hexdigest() != source.sha256:
            raise BundleError(
                f"source file changed during final verification: {source.relative_path}"
            )
    return tuple(sources)


def _canonical_json(value: object) -> bytes:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (encoded + "\n").encode("utf-8")


def _manifest(root: Path, sources: tuple[SourceFile, ...]) -> tuple[dict[str, object], bytes]:
    file_records = [
        {
            "path": source.relative_path,
            "mode": format(source.mode, "04o"),
            "size_bytes": len(source.data),
            "sha256": source.sha256,
        }
        for source in sources
    ]
    tree_sha256 = hashlib.sha256(_canonical_json(file_records)).hexdigest()
    value: dict[str, object] = {
        "schema_version": "r2sp.source-bundle.v1",
        "git_head": _git(root, "rev-parse", "HEAD").decode("ascii").strip(),
        "source_tree_sha256": tree_sha256,
        "file_count": len(file_records),
        "files": file_records,
    }
    encoded = _canonical_json(value)
    return value, encoded


def _add_member(archive: tarfile.TarFile, name: str, data: bytes, mode: int) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    info.mode = mode
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    archive.addfile(info, io.BytesIO(data))


def _archive_bytes(sources: tuple[SourceFile, ...], manifest_bytes: bytes) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.GNU_FORMAT) as archive:
        for source in sources:
            _add_member(
                archive,
                f"{BUNDLE_PREFIX}/{source.relative_path}",
                source.data,
                source.mode,
            )
        _add_member(archive, f"{BUNDLE_PREFIX}/{MANIFEST_NAME}", manifest_bytes, 0o444)
    return output.getvalue()


def _default_output_dir() -> Path:
    return Path("/usr/xtmp") / getuser() / "skill-creation" / "source-bundles"


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _write_once(path: Path, data: bytes, expected_sha256: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not path.is_file():
            raise BundleError(f"bundle target exists and is not a file: {path}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected_sha256:
            raise BundleError(f"existing bundle has a different digest: {path}")
        return

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".source-bundle-",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o444)
        try:
            os.link(temporary, path)
        except FileExistsError:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected_sha256:
                raise BundleError(f"concurrent bundle has a different digest: {path}") from None
    finally:
        if temporary.exists():
            temporary.unlink()


def build(*, root: Path, output_dir: Path, write: bool) -> dict[str, object]:
    root = root.resolve(strict=True)
    output_dir = output_dir.expanduser().resolve(strict=False)
    if _inside(output_dir, root):
        raise BundleError("the bundle output directory must be outside the source repository")

    sources = _read_sources(root)
    manifest, manifest_bytes = _manifest(root, sources)
    archive = _archive_bytes(sources, manifest_bytes)
    bundle_sha256 = hashlib.sha256(archive).hexdigest()
    target = output_dir / f"skill-creation-{manifest['source_tree_sha256']}.tar"
    if write:
        _write_once(target, archive, bundle_sha256)

    return {
        "schema_version": "r2sp.source-bundle-result.v1",
        "dry_run": not write,
        "bundle_path": str(target),
        "bundle_sha256": bundle_sha256,
        "bundle_size_bytes": len(archive),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "source_tree_sha256": manifest["source_tree_sha256"],
        "git_head": manifest["git_head"],
        "file_count": manifest["file_count"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--output-dir", type=Path, default=_default_output_dir())
    parser.add_argument(
        "--write",
        action="store_true",
        help="persist the bundle; without this flag only compute and print its identity",
    )
    arguments = parser.parse_args()
    try:
        result = build(
            root=arguments.repository_root,
            output_dir=arguments.output_dir,
            write=arguments.write,
        )
    except (BundleError, OSError) as exc:
        error = json.dumps({"status": "INVALID", "reason": str(exc)}, sort_keys=True)
        print(error, file=sys.stderr)
        return 2
    print(json.dumps({"status": "SUCCESS", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
