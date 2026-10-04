#!/usr/bin/env python3
"""Prepare and seal the user-owned runtime for the explicitly approved demo."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

EXPERIMENT = Path(__file__).resolve().parent.parent
RUNTIME = EXPERIMENT / "runtime"
ROOTFS = EXPERIMENT / "data" / "bubblewrap" / "rootfs"
LOCK = RUNTIME / "bubblewrap-lock.json"
REQUIREMENTS = RUNTIME / "requirements.lock"
VERSION = [3, 11, 14]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(root: Path) -> tuple[dict[str, str], dict[str, str]]:
    files, symlinks = {}, {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            target = os.readlink(path)
            if Path(target).is_absolute() or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError(f"runtime symlink escapes rootfs: {relative}")
            symlinks[relative] = target
        elif path.is_file():
            files[relative] = sha256(path)
        elif not path.is_dir():
            raise ValueError(f"runtime contains a special file: {relative}")
    return files, symlinks


def copy_libraries(root: Path) -> None:
    """Resolve trusted interpreter/wheel ELF dependencies and copy only their files."""
    pending = []
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            with path.open("rb") as stream:
                if stream.read(4) == b"\x7fELF":
                    pending.append(path)
    visited = set()
    while pending:
        binary = pending.pop()
        if binary in visited:
            continue
        visited.add(binary)
        result = subprocess.run(
            ["ldd", str(binary)],
            capture_output=True,
            text=True,
            check=False,
            env={"PATH": os.defpath, "LD_LIBRARY_PATH": str(root / "usr" / "local" / "lib")},
        )
        if "not found" in result.stdout:
            raise RuntimeError(f"unresolved shared library in {binary.relative_to(root)}")
        for match in re.finditer(r"(?:=>\s+|^\s*)(/[^\s]+)\s+\(", result.stdout, re.MULTILINE):
            source = Path(match.group(1))
            if source.is_relative_to(root):
                continue
            destination = root / source.relative_to("/")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                shutil.copy2(source.resolve(strict=True), destination)
                pending.append(destination)


def check_runtime(root: Path) -> dict:
    code = (
        "import json,sys,numpy,pandas,pytest;"
        "print(json.dumps({'python':list(sys.version_info[:3]),"
        "'numpy':numpy.__version__,'pandas':pandas.__version__,'pytest':pytest.__version__}))"
    )
    command = [
        "bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--clearenv",
        "--ro-bind",
        str(root),
        "/",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--tmpfs",
        "/work",
        "--uid",
        "65534",
        "--gid",
        "65534",
        "--setenv",
        "PATH",
        "/usr/local/bin",
        "--setenv",
        "OPENBLAS_NUM_THREADS",
        "1",
        "--setenv",
        "LD_LIBRARY_PATH",
        "/usr/local/lib",
        "--chdir",
        "/work",
        "/usr/local/bin/python",
        "-I",
        "-B",
        "-c",
        code,
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=True)
    measured = json.loads(result.stdout)
    expected = {"python": VERSION, "numpy": "2.2.6", "pandas": "2.2.3", "pytest": "8.4.2"}
    if measured != expected:
        raise RuntimeError("actual Bubblewrap imports differ from the pinned runtime")
    return measured


def main() -> None:
    dependency_hash = sha256(REQUIREMENTS)
    if LOCK.exists():
        lock = json.loads(LOCK.read_text())
        files, symlinks = manifest(ROOTFS)
        if (
            lock.get("dependency_hash") != dependency_hash
            or lock.get("files") != files
            or lock.get("symlinks", {}) != symlinks
            or lock.get("python_version") != VERSION
        ):
            raise ValueError("existing runtime lock does not match; preserve it for inspection")
        check_runtime(ROOTFS)
        print(
            json.dumps(
                {"ready": True, "reused": True, "rootfs": str(ROOTFS), "lock_sha256": sha256(LOCK)}
            )
        )
        return

    install_dir = Path.home() / ".local" / "share" / "uv" / "python"
    subprocess.run(
        [
            "uv",
            "python",
            "install",
            "3.11.14",
            "--no-bin",
            "--install-dir",
            str(install_dir),
            "--no-progress",
        ],
        check=True,
    )
    source = install_dir / "cpython-3.11.14-linux-x86_64-gnu"
    if not (source / "bin" / "python3.11").is_file():
        raise RuntimeError("the demo requires the downloaded Linux amd64 Python 3.11.14")
    stage = ROOTFS.with_name(".rootfs-preparing")
    if stage.is_symlink():
        raise ValueError("runtime staging directory must not be a symlink")
    if stage.exists():
        shutil.rmtree(stage)
    for name in ("usr/local/bin", "bundle", "work", "tmp", "proc", "dev", "etc"):
        (stage / name).mkdir(parents=True, exist_ok=True)
    prefix = stage / "usr" / "local"
    shutil.copy2(source / "bin" / "python3.11", prefix / "bin" / "python3.11")
    (prefix / "bin" / "python").symlink_to("python3.11")
    (prefix / "bin" / "python3").symlink_to("python3.11")
    shutil.copytree(source / "lib", prefix / "lib", symlinks=True)
    site_packages = prefix / "lib" / "python3.11" / "site-packages"
    shutil.rmtree(site_packages)
    site_packages.mkdir()
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(prefix / "bin" / "python3.11"),
            "--target",
            str(site_packages),
            "--require-hashes",
            "--only-binary",
            ":all:",
            "--link-mode",
            "copy",
            "--no-progress",
            "-r",
            str(REQUIREMENTS),
        ],
        check=True,
    )
    (stage / "etc" / "passwd").write_text(
        "nobody:x:65534:65534:nobody:/work:/usr/local/bin/python\n"
    )
    (stage / "etc" / "group").write_text("nogroup:x:65534:\n")
    (stage / "etc" / "nsswitch.conf").write_text("passwd: files\ngroup: files\nhosts: files\n")
    for path in sorted(stage.rglob("__pycache__"), reverse=True):
        shutil.rmtree(path)
    copy_libraries(stage)
    measured = check_runtime(stage)
    files, symlinks = manifest(stage)
    if ROOTFS.exists():
        raise ValueError("unsealed rootfs already exists; preserve it for inspection")
    stage.rename(ROOTFS)
    lock = {
        "rootfs": "../data/bubblewrap/rootfs",
        "files": files,
        "symlinks": symlinks,
        "python_version": VERSION,
        "dependency_hash": dependency_hash,
        "aggregate_limits_enforced": False,
    }
    temporary = LOCK.with_suffix(".tmp")
    with temporary.open("w") as stream:
        json.dump(lock, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(LOCK)
    print(
        json.dumps(
            {
                "ready": True,
                "reused": False,
                "rootfs": str(ROOTFS),
                "lock_sha256": sha256(LOCK),
                "files": len(files),
                "symlinks": len(symlinks),
                "imports": measured,
                "aggregate_limits_enforced": False,
            }
        )
    )


if __name__ == "__main__":
    main()
