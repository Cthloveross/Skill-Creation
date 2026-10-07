"""Pinned SkillsBench inputs, shared public retrieval pool and task adapter."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import posixpath
import re
import shlex
import shutil
import struct
import subprocess
import tempfile
import time
import urllib.request
import uuid
import zipfile
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import tomllib

from .artifacts import atomic_json
from .container import _safe_path

_EVOLUTION_PRIVATE_ROOTS = ("/bundle", "/work/candidate", "/work/scratch", "/work/observations")

COMMIT = "4380d4bff673dd6e1d58e5babeb2aaa0fe527119"
REPOSITORY = "Zhang-Henry/CoEvoSkills"
TASK_COUNT = 85


def _hash(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(part)
    return value.hexdigest()


def _json_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _public_link_target(relative: str, target: str, roots: Sequence[str]) -> bool:
    resolved = posixpath.normpath(
        target
        if target.startswith("/")
        else posixpath.join("/", posixpath.dirname(relative), target)
    )
    if any(part in {"skills", ".claude", ".codex", ".evolution"} for part in resolved.split("/")):
        return False
    if any(
        resolved == private or resolved.startswith(private + "/")
        for private in (*_EVOLUTION_PRIVATE_ROOTS, "/tests", "/logs/verifier", "/root/verifier")
    ):
        return False
    # Preserve workspace links and task-image executable links without dereferencing
    # them on the host. Verifier mounts contain no host filesystem targets.
    return any(
        resolved == root or resolved.startswith(root.rstrip("/") + "/")
        for root in (*roots, "/usr", "/bin", "/lib", "/lib64")
    )


def task_config(directory: Path) -> dict[str, Any]:
    """Apply the defaults and legacy size units of the author's pinned Harbor config."""
    value = tomllib.loads((directory / "task.toml").read_text())
    environment = {
        "build_timeout_sec": 600.0,
        "cpus": 1,
        "memory_mb": 2048,
        "storage_mb": 10240,
        "gpus": 0,
        "allow_internet": True,
        **value.get("environment", {}),
    }
    for old, new in (("memory", "memory_mb"), ("storage", "storage_mb")):
        if old in environment:
            size = str(environment.pop(old)).strip().upper()
            match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)([GMK])", size)
            if match is None:
                raise ValueError("skillsbench_invalid_resource_size")
            number, unit = match.groups()
            environment[new] = int(float(number) * {"G": 1024, "M": 1, "K": 1 / 1024}[unit])
    for name in ("cpus", "memory_mb", "storage_mb"):
        if isinstance(environment[name], bool) or environment[name] <= 0:
            raise ValueError("skillsbench_invalid_resource_limit")
    if not isinstance(environment["allow_internet"], bool):
        raise ValueError("skillsbench_invalid_network_setting")
    value["environment"] = environment
    value["agent"] = {"timeout_sec": 600.0, **value.get("agent", {})}
    value["verifier"] = {"timeout_sec": 600.0, "env": {}, **value.get("verifier", {})}
    return value


PRIVATE_SEGMENTS = frozenset(
    {
        "groundtruth",
        "ground_truth",
        "solutions",
        "solution",
        "answers",
        "answer",
        "grader",
        "grading",
        "skills",
        ".claude",
        ".codex",
        ".opencode",
        ".agents",
        ".goose",
        ".factory",
        ".gemini",
    }
)


def _private_path(path: str) -> bool:
    parts = Path(path).parts
    return any(p.lower() in PRIVATE_SEGMENTS for p in parts)


def _docker_ignored(path: str, patterns: Sequence[str]) -> bool:
    ignored = False
    for raw in patterns:
        pattern = raw.strip()
        if not pattern or pattern.startswith("#"):
            continue
        negate = pattern.startswith("!")
        pattern = pattern.lstrip("!").strip("/")
        if any(fnmatch.fnmatch(path, p) for p in (pattern, pattern + "/**")):
            ignored = not negate
    return ignored


def _environment_inputs(directory: Path) -> dict[str, Any]:
    """Positive list from local COPY/ADD, excluding private build context explicitly."""
    environment = directory / "environment"
    recipe = (environment / "Dockerfile").read_text()
    instructions = re.sub(r"\\\n[ \t]*", " ", recipe).splitlines()
    ignore_file = environment / ".dockerignore"
    ignored = ignore_file.read_text().splitlines() if ignore_file.exists() else []
    variables, workdir, copies, errors, private_copied = {}, "/", [], [], []
    for line in instructions:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        operation, _, value = line.partition(" ")
        operation = operation.upper()
        if operation == "FROM":
            workdir, variables = "/", {}
        elif operation == "ENV":
            for word in shlex.split(value):
                if "=" in word:
                    name, setting = word.split("=", 1)
                    variables[name] = setting
        elif operation == "WORKDIR":
            for name, setting in variables.items():
                value = value.replace("${" + name + "}", setting).replace("$" + name, setting)
            workdir = value if value.startswith("/") else workdir.rstrip("/") + "/" + value
        elif operation in {"COPY", "ADD"}:
            words = json.loads(value) if value.startswith("[") else shlex.split(value)
            if any(w.startswith("--from=") for w in words):
                continue  # Image-stage content is not local public input.
            words = [w for w in words if not w.startswith("--")]
            if len(words) < 2:
                errors.append("unresolved_copy:" + line)
                continue
            destination = words[-1]
            if not destination.startswith("/"):
                destination = workdir.rstrip("/") + "/" + destination
            for source in words[:-1]:
                if source.startswith(("http://", "https://")):
                    errors.append("remote_add:" + source)
                    continue
                if "$" in source or "$" in destination or ".." in Path(source).parts:
                    errors.append("unresolved_copy:" + line)
                    continue
                matches = list(environment.glob(source.rstrip("/")))
                if not matches:
                    errors.append("unmatched_copy:" + source)
                for candidate in matches:
                    paths = candidate.rglob("*") if candidate.is_dir() else [candidate]
                    for file in paths:
                        if not file.is_file() or file.is_symlink():
                            continue
                        relative = file.relative_to(environment).as_posix()
                        if _docker_ignored(relative, ignored):
                            continue
                        if _private_path(relative):
                            private_copied.append(relative)
                            continue
                        suffix = (
                            file.relative_to(candidate).as_posix()
                            if candidate.is_dir()
                            else file.name
                        )
                        target = destination
                        if candidate.is_dir() or destination.endswith("/") or len(words) > 2:
                            target = destination.rstrip("/") + "/" + suffix
                        copies.append({"source": relative, "destination": target})
    roots = {"/root", "/" + workdir.strip("/").split("/")[0]}
    for destination in [x["destination"] for x in copies]:
        top = "/" + destination.strip("/").split("/")[0]
        if top not in {"/usr", "/bin", "/lib", "/lib64", "/etc", "/tmp"}:
            roots.add(top)
    instruction = (directory / "instruction.md").read_text()
    for value in re.findall(
        r"/(?:root|app|workspace|home|data|output|outputs|opt|services)(?:/[A-Za-z0-9_.-]+)*",
        instruction,
    ):
        roots.add("/" + value.strip("/").split("/")[0])
    roots.discard("/")
    copies = sorted({(x["source"], x["destination"]) for x in copies})
    return {
        "workdir": workdir,
        "copies": [{"source": s, "destination": d} for s, d in copies],
        "unresolved": errors,
        "private_copied": sorted(set(private_copied)),
        "workspace_roots": sorted(roots),
    }


def _public_path(path: str, environments: Mapping[str, Any]) -> tuple[str, str] | None:
    parts = path.split("/")
    if len(parts) == 3 and parts[0] == "tasks" and parts[2] == "instruction.md":
        return parts[1], "instruction.md"
    if len(parts) >= 4 and parts[0] == "tasks" and parts[2] == "environment":
        relative = "/".join(parts[3:])
        visible = {x["source"] for x in environments[parts[1]]["copies"]}
        if relative == "Dockerfile" or relative in visible:
            return parts[1], "environment/" + relative
    if (
        len(parts) >= 4
        and parts[:2] == ["artifacts", "background_docs"]
        and not _private_path("/".join(parts[3:]))
    ):
        return parts[2], "background/" + "/".join(parts[3:])
    return None


def _binary_summary(path: Path) -> dict[str, Any]:
    """Describe public structure; never execute embedded code or infer task answers."""
    suffix = path.suffix.lower()
    value: dict[str, Any] = {"format": suffix.lstrip(".") or "unknown"}
    if suffix in {".zip", ".xlsx", ".pptx", ".docx"}:
        try:
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                value.update(
                    supported=True,
                    entries=[{"path": e.filename, "bytes": e.file_size} for e in entries],
                )
        except (OSError, zipfile.BadZipFile):
            value.update(supported=False, reason="invalid_zip_structure")
    elif suffix == ".stl":
        with path.open("rb") as stream:
            header = stream.read(84)
            triangles = struct.unpack("<I", header[80:84])[0] if len(header) == 84 else None
            if triangles is not None and path.stat().st_size == 84 + 50 * triangles:
                materials = set()
                for _ in range(triangles):
                    materials.add(struct.unpack("<H", stream.read(50)[48:50])[0])
                value.update(
                    supported=True,
                    encoding="binary",
                    triangles=triangles,
                    attribute_values=sorted(materials),
                )
            else:
                value.update(supported=False, reason="unrecognized_stl_structure")
    elif suffix == ".png":
        with path.open("rb") as stream:
            header = stream.read(24)
        if header[:8] == b"\x89PNG\r\n\x1a\n" and len(header) == 24:
            value.update(
                supported=True,
                width=struct.unpack(">I", header[16:20])[0],
                height=struct.unpack(">I", header[20:24])[0],
            )
        else:
            value.update(supported=False, reason="invalid_png_header")
    else:
        value.update(supported=False, reason="no_deterministic_structure_reader")
    return value


def prepare_skillsbench(root: Path, token_counter: Any = None) -> dict[str, Any]:
    """Download only task trees/background docs/legal files, then seal public inputs."""
    root = Path(root).resolve()
    data, checkout = root / "data/skillsbench", root / "data/upstream/coevo-skills"
    data.mkdir(parents=True, exist_ok=True)
    tree_path = data / "source-tree.json"
    if tree_path.exists():
        tree = json.loads(tree_path.read_text())
    else:
        url = f"https://api.github.com/repos/{REPOSITORY}/git/trees/{COMMIT}?recursive=1"
        with urllib.request.urlopen(url, timeout=60) as response:
            tree = json.load(response)
        atomic_json(tree_path, tree)
    if tree.get("sha") != COMMIT or tree.get("truncated") is not False:
        raise ValueError("skillsbench_source_tree_invalid")
    task_ids = sorted(
        {e["path"].split("/")[1] for e in tree["tree"] if e["path"].startswith("tasks/")}
    )
    if len(task_ids) != TASK_COUNT:
        raise ValueError("skillsbench_task_population_changed")
    files = [
        e
        for e in tree["tree"]
        if e["type"] == "blob"
        and (
            e["path"].startswith("tasks/")
            or e["path"].startswith("artifacts/background_docs/")
            or e["path"] in {"NOTICE", "LICENSE"}
        )
    ]

    def download(entry: Mapping[str, Any]) -> dict[str, Any]:
        relative = entry["path"]
        target = checkout / _safe_path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file():
            temp = target.with_name(target.name + ".downloading")
            url = f"https://raw.githubusercontent.com/{REPOSITORY}/{COMMIT}/{relative}"
            with urllib.request.urlopen(url, timeout=120) as response, temp.open("wb") as stream:
                while part := response.read(1024 * 1024):
                    stream.write(part)
            os.replace(temp, target)
        blob = hashlib.sha1(f"blob {target.stat().st_size}\0".encode())
        with target.open("rb") as stream:
            for part in iter(lambda: stream.read(1024 * 1024), b""):
                blob.update(part)
        if blob.hexdigest() != entry["sha"]:
            raise ValueError(f"skillsbench_source_blob_mismatch:{relative}")
        return {
            "path": relative,
            "sha256": _hash(target),
            "git_blob": entry["sha"],
            "bytes": target.stat().st_size,
        }

    with ThreadPoolExecutor(max_workers=8) as executor:
        sealed = sorted(executor.map(download, files), key=lambda e: e["path"])
    source = {"repository": REPOSITORY, "commit": COMMIT, "tasks": task_ids, "files": sealed}
    atomic_json(data / "source-manifest.json", source)
    environments = {task: _environment_inputs(checkout / "tasks" / task) for task in task_ids}
    public = []
    for entry in sealed:
        selected = _public_path(entry["path"], environments)
        if selected is None:
            continue
        task, relative = selected
        path = checkout / entry["path"]
        try:
            with path.open("r", encoding="utf-8") as stream:
                text = stream.read()
            if "\0" in text:
                raise UnicodeError("binary")
            kind, summary = "text", None
        except (UnicodeError, OSError):
            kind, summary = "binary", _binary_summary(path)
        public.append(
            {
                **entry,
                "task_id": task,
                "relative_path": relative,
                "document_id": f"{task}::{relative}",
                "kind": kind,
                "summary": summary,
            }
        )
    manifest = {
        "schema": "skillsbench.public.v1",
        "repository": REPOSITORY,
        "commit": COMMIT,
        "tasks": task_ids,
        "files": public,
        "source_manifest_hash": _json_hash(source),
        "environments": environments,
        "private_segments": sorted(PRIVATE_SEGMENTS),
        "excluded_environment_files": [
            {
                "path": e["path"],
                "reason": "private_path"
                if _private_path(e["path"])
                else "not_copied_or_dockerignored",
            }
            for e in sealed
            if "/environment/" in e["path"] and _public_path(e["path"], environments) is None
        ],
    }
    manifest["manifest_hash"] = _json_hash(manifest)
    atomic_json(data / "public-manifest.json", manifest)
    if token_counter is not None:
        prepare_pool(root, token_counter)
    return {
        "ready": True,
        "tasks": len(task_ids),
        "source_files": len(sealed),
        "public_files": len(public),
        "manifest_hash": manifest["manifest_hash"],
    }


class SkillsBenchSource:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.checkout = self.root / "data/upstream/coevo-skills"
        self.manifest = json.loads(
            (self.root / "data/skillsbench/public-manifest.json").read_text()
        )

    def validate(self) -> None:
        m = self.manifest
        if (
            m.get("commit") != COMMIT
            or len(m.get("tasks", [])) != TASK_COUNT
            or len(set(m["tasks"])) != TASK_COUNT
            or m.get("manifest_hash")
            != _json_hash({k: v for k, v in m.items() if k != "manifest_hash"})
        ):
            raise ValueError("skillsbench_public_manifest_invalid")
        actual_environments = {
            task: _environment_inputs(self.checkout / "tasks" / task) for task in m["tasks"]
        }
        if actual_environments != m.get("environments"):
            raise ValueError("skillsbench_public_copy_manifest_mismatch")
        for entry in m["files"]:
            if _public_path(entry["path"], m["environments"]) != (
                entry["task_id"],
                entry["relative_path"],
            ):
                raise ValueError("skillsbench_private_file_in_public_manifest")
            path = self.checkout / _safe_path(entry["path"])
            if path.is_symlink() or _hash(path) != entry["sha256"]:
                raise ValueError("skillsbench_public_file_hash_mismatch")
        source = json.loads((self.root / "data/skillsbench/source-manifest.json").read_text())
        if _json_hash(source) != m["source_manifest_hash"] or source["commit"] != COMMIT:
            raise ValueError("skillsbench_source_manifest_invalid")
        for entry in source["files"]:
            path = self.checkout / _safe_path(entry["path"])
            if path.is_symlink() or _hash(path) != entry["sha256"]:
                raise ValueError("skillsbench_source_file_hash_mismatch")

    def task(self, task_id: str) -> dict[str, Any]:
        if task_id not in self.manifest["tasks"]:
            raise ValueError("unknown_skillsbench_task")
        directory = self.checkout / "tasks" / task_id
        config = task_config(directory)
        inputs = [
            e
            for e in self.manifest["files"]
            if e["task_id"] == task_id
            and e["relative_path"].startswith("environment/")
            and e["relative_path"] != "environment/Dockerfile"
        ]
        return {
            "task_id": task_id,
            "opening": (directory / "instruction.md").read_text(),
            "public_input_manifest": [
                {
                    **{k: e[k] for k in ("relative_path", "sha256", "bytes")},
                    "sandbox_paths": [
                        x["destination"]
                        for x in self.manifest["environments"][task_id]["copies"]
                        if "environment/" + x["source"] == e["relative_path"]
                    ],
                }
                for e in inputs
            ],
            "environment": {
                **self.manifest["environments"][task_id],
                **config.get("environment", {}),
            },
        }


def prepare_pool(root: Path, tokenizer: Any) -> dict[str, Any]:
    """Pool background documents; task instructions and inputs stay task-local."""
    source = SkillsBenchSource(root)
    source.validate()
    output = source.root / "data/skillsbench/corpus"
    output.mkdir(parents=True, exist_ok=True)
    pages = []
    for entry in source.manifest["files"]:
        if not entry["relative_path"].startswith("background/"):
            continue
        original = source.checkout / entry["path"]
        if entry["kind"] == "text":
            text = original.read_text(encoding="utf-8")
        else:
            text = json.dumps(
                {
                    "file": entry["relative_path"],
                    "bytes": entry["bytes"],
                    "sha256": entry["sha256"],
                    "structure": entry["summary"],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        if not text:
            text = json.dumps(
                {
                    "file": entry["relative_path"],
                    "bytes": 0,
                    "sha256": entry["sha256"],
                    "empty": True,
                },
                sort_keys=True,
            )
        tokens = tokenizer.encode(text, add_special_tokens=False)
        if hasattr(tokens, "ids"):
            tokens = tokens.ids
        for start in range(0, max(1, len(tokens)), 1920):
            window = tokens[start : start + 2048]
            content = tokenizer.decode(window, skip_special_tokens=False)
            page_id = f"{entry['document_id']}::tokens-{start}-{start + len(window)}"
            page = {
                "page_id": page_id,
                "title": entry["document_id"],
                "body": content,
                "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                "source_sha256": entry["sha256"],
                "source_document_id": entry["document_id"],
                "token_start": start,
                "token_end": start + len(window),
            }
            filename = hashlib.sha256(page_id.encode()).hexdigest() + ".json"
            atomic_json(output / filename, page)
            pages.append(
                {
                    "file": filename,
                    **{
                        k: page[k]
                        for k in (
                            "page_id",
                            "content_sha256",
                            "source_sha256",
                            "token_start",
                            "token_end",
                        )
                    },
                }
            )
            if start + 2048 >= len(tokens):
                break
    if not pages:
        raise ValueError("skillsbench_background_pool_empty")
    manifest = {
        "schema": "skillsbench.pool.v2",
        "scope": "background_docs_only",
        "source_manifest_hash": source.manifest["manifest_hash"],
        "tokenizer": "Qwen/Qwen3-Embedding-4B",
        "revision": "5cf2132abc99cad020ac570b19d031efec650f2b",
        "chunk_tokens": 2048,
        "overlap_tokens": 128,
        "pages": pages,
    }
    manifest["corpus_hash"] = _json_hash(manifest)
    atomic_json(output / "manifest.json", manifest)
    return {"pages": len(pages), "corpus_hash": manifest["corpus_hash"]}


def validate_pool(root: Path, source: SkillsBenchSource | None = None) -> dict[str, Any]:
    source = source or SkillsBenchSource(root)
    directory = Path(root) / "data/skillsbench/corpus"
    manifest = json.loads((directory / "manifest.json").read_text())
    if (
        manifest.get("schema") != "skillsbench.pool.v2"
        or manifest.get("scope") != "background_docs_only"
        or manifest.get("source_manifest_hash") != source.manifest["manifest_hash"]
        or manifest.get("chunk_tokens") != 2048
        or manifest.get("overlap_tokens") != 128
        or manifest.get("tokenizer") != "Qwen/Qwen3-Embedding-4B"
        or manifest.get("revision") != "5cf2132abc99cad020ac570b19d031efec650f2b"
        or manifest.get("corpus_hash")
        != _json_hash({k: v for k, v in manifest.items() if k != "corpus_hash"})
    ):
        raise ValueError("skillsbench_pool_manifest_invalid")
    originals = {
        e["document_id"]: e["sha256"]
        for e in source.manifest["files"]
        if e["relative_path"].startswith("background/")
        and e["path"].startswith("artifacts/background_docs/")
    }
    seen = set()
    for record in manifest["pages"]:
        value = json.loads((directory / _safe_path(record["file"])).read_text())
        if (
            value["source_document_id"] not in originals
            or value["source_sha256"] != originals[value["source_document_id"]]
            or value["source_sha256"] != record["source_sha256"]
            or hashlib.sha256(value["body"].encode()).hexdigest() != record["content_sha256"]
            or value["content_sha256"] != record["content_sha256"]
            or value["page_id"] != record["page_id"]
            or value["token_end"] - value["token_start"] > 2048
        ):
            raise ValueError("skillsbench_corpus_hash_mismatch")
        seen.add(value["source_document_id"])
    if not originals or seen != set(originals):
        raise ValueError("skillsbench_background_pool_incomplete")
    return manifest


def prepare_corpus(spec: Any) -> Any:
    from .core import DeterministicBM25, FullDocumentHybridSession, Page
    from .dense import DenseIndex, OpenAICompatibleEmbeddingClient
    from .retrieval import text_counter

    root = spec.root / "data/skillsbench/corpus"
    manifest = validate_pool(spec.root)
    pages = []
    for record in manifest["pages"]:
        value = json.loads((root / _safe_path(record["file"])).read_text())
        if hashlib.sha256(value["body"].encode()).hexdigest() != record["content_sha256"]:
            raise ValueError("skillsbench_corpus_hash_mismatch")
        pages.append(Page(value["page_id"], value["title"], value["body"], value["content_sha256"]))
    pages = tuple(pages)
    embedding = spec.values["embedding"]
    client = OpenAICompatibleEmbeddingClient(
        embedding["endpoint"],
        model_id=embedding["model"],
        revision=embedding["revision"],
        dimensions=embedding["dimension"],
    )
    cache = spec.root / "data/skillsbench/dense" / manifest["corpus_hash"]
    if not cache.exists():
        subprocess.run(
            [
                str((spec.root / embedding["vllm"]).parent / "python"),
                str(spec.root / "scripts/prepare_skillsbench.py"),
                "--index-settings",
                json.dumps(embedding),
            ],
            check=True,
            capture_output=True,
            timeout=spec.values["runtime"]["episode_timeout_seconds"],
        )
    dense = DenseIndex.load_cache(cache, pages, client=client)
    return FullDocumentHybridSession(
        DeterministicBM25(pages),
        dense,
        text_counter(spec),
        wire_token_budget=spec.values["retrieval"]["wire_token_limit"],
    )


def prepare_dense(root: Path, embedding: Mapping[str, Any]) -> dict[str, Any]:
    from .core import Page
    from .dense import DenseIndex, HuggingFaceQwenTokenizer, OpenAICompatibleEmbeddingClient

    directory = Path(root) / "data/skillsbench/corpus"
    started = time.monotonic()
    manifest = validate_pool(root)
    pages = []
    for record in manifest["pages"]:
        value = json.loads((directory / _safe_path(record["file"])).read_text())
        pages.append(Page(value["page_id"], value["title"], value["body"], value["content_sha256"]))
    pages.sort(key=lambda p: p.page_id)
    cache = Path(os.environ.get("HF_HOME", str(Path.home() / ".cache/huggingface")))
    tokenizer = HuggingFaceQwenTokenizer.from_pretrained(
        cache_dir=str(cache / "hub"),
        local_files_only=True,
        model_id=embedding["model"],
        revision=embedding["revision"],
        dimensions=embedding["dimension"],
    )
    client = OpenAICompatibleEmbeddingClient(
        embedding["endpoint"],
        model_id=embedding["model"],
        revision=embedding["revision"],
        dimensions=embedding["dimension"],
    )
    output = Path(root) / "data/skillsbench/dense" / manifest["corpus_hash"]
    parts = output.parent / (manifest["corpus_hash"] + "-parts")
    parts.mkdir(parents=True, exist_ok=True)
    if (output / "manifest.json").exists():
        DenseIndex.load_cache(output, pages, client=client, tokenizer=tokenizer)
        return {
            "ready": True,
            "reused": True,
            "pages": len(pages),
            "corpus_hash": manifest["corpus_hash"],
        }
    batch_manifests = []
    # Independent sealed caches preserve completed free embedding requests across restarts.
    for offset in range(0, len(pages), 256):
        batch = tuple(pages[offset : offset + 256])
        target = parts / str(offset)
        if (target / "manifest.json").exists():
            DenseIndex.load_cache(target, batch, client=client, tokenizer=tokenizer)
            batch_manifest = json.loads((target / "manifest.json").read_text())
        else:
            if target.exists():
                shutil.rmtree(target)  # Incomplete local cache, never exposed to any learner.
            index = DenseIndex.build(batch, client=client, tokenizer=tokenizer)
            batch_manifest = index.save_cache(target)
        batch_manifests.append(batch_manifest)
        atomic_json(
            output.parent / "progress.json",
            {
                "corpus_hash": manifest["corpus_hash"],
                "completed_pages": min(offset + 256, len(pages)),
                "total_pages": len(pages),
                "seconds": time.monotonic() - started,
            },
        )
    from .core._canonical import canonical_json_bytes, canonical_json_sha256

    output.mkdir(exist_ok=True)
    vectors = output / "vectors.f32"
    temporary = vectors.with_suffix(".preparing")
    with temporary.open("wb") as stream:
        for offset in range(0, len(pages), 256):
            with (parts / str(offset) / "vectors.f32").open("rb") as part:
                shutil.copyfileobj(part, stream)
    contract = dict(batch_manifests[0]["contract"])
    contract["pages"] = [p for m in batch_manifests for p in m["contract"]["pages"]]
    contract["page_count"] = len(pages)
    # The whole-corpus hash is part of the shared DenseIndex cache contract.
    contract["corpus_hash"] = canonical_json_sha256(
        [
            {"page_id": p.page_id, "title": p.title, "content_sha256": p.content_sha256}
            for p in pages
        ]
    )
    unsigned = {
        **{
            k: v
            for k, v in batch_manifests[0].items()
            if k not in {"manifest_payload_sha256", "contract", "vectors"}
        },
        "contract": contract,
        "vectors": {
            **batch_manifests[0]["vectors"],
            "shape": [len(pages), client.dimensions],
            "size_bytes": temporary.stat().st_size,
            "sha256": _hash(temporary),
        },
    }
    os.replace(temporary, vectors)
    sealed = {**unsigned, "manifest_payload_sha256": canonical_json_sha256(unsigned)}
    metadata = output / "manifest.preparing"
    metadata.write_bytes(canonical_json_bytes(sealed) + b"\n")
    os.replace(metadata, output / "manifest.json")
    result = {
        "ready": True,
        "pages": len(pages),
        "corpus_hash": manifest["corpus_hash"],
        "seconds": time.monotonic() - started,
        "vectors_bytes": vectors.stat().st_size,
    }
    atomic_json(Path(root) / "data/skillsbench/dense/readiness.json", result)
    return result


EXECUTION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_terminal_command",
            "description": "Run bash in the fresh task sandbox.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_skill_file",
            "description": "Read a file from the current Skill package.",
            "parameters": {
                "type": "object",
                "properties": {"relative_path": {"type": "string"}},
                "required": ["relative_path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_skill_script",
            "description": "Run a packaged Python script with JSON stdin.",
            "parameters": {
                "type": "object",
                "properties": {"relative_path": {"type": "string"}, "input_json": {}},
                "required": ["relative_path", "input_json"],
                "additionalProperties": False,
            },
        },
    },
]


def _open_permissions(directory: Path) -> None:
    """Make root-owned executor artifacts readable to the host via a cleanup container."""
    directory = Path(directory)
    if not directory.is_absolute() or not directory.is_dir() or directory.is_symlink():
        raise ValueError("skillsbench_artifact_directory_invalid")
    from .container import CLEANUP_IMAGE

    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--mount",
            f"type=bind,src={directory},dst=/tau-artifacts",
            CLEANUP_IMAGE,
            "sh",
            "-c",
            "chmod -R a+rX /tau-artifacts",
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )


class SkillsBenchAdapter:
    """Keep creation public and execute/oracle/evaluate in separate fresh environments."""

    def __init__(
        self,
        spec: Any,
        task: str,
        *,
        demo: bool,
        model_factory: Any = None,
        counter: Any = None,
        artifact_root: Path | None = None,
        model_journal_dir: Path | None = None,
        runtime: str | None = None,
    ):
        from .skillsbench_runtime import SkillsBenchRunner

        self.spec, self.task_id, self.demo = spec, task, demo
        self.source = SkillsBenchSource(spec.root)
        self.public_inputs = self.source.task(task)
        selected_lock = getattr(spec, "values", {}).get("source", {}).get("runtime_lock")
        self.runner = SkillsBenchRunner(
            spec.root,
            task,
            demo=demo,
            runtime=runtime,
            runtime_lock_path=spec.root / selected_lock if selected_lock else None,
        )
        self.public_inputs["environment"]["execution_runtime"] = self.runner.runtime
        self.public_inputs["environment"]["runtime_network"] = (
            "bridge"
            if not self.runner.use_bwrap
            and self.public_inputs["environment"].get("allow_internet") is True
            else "none"
        )
        self.model_factory, self.counter = model_factory, counter
        self.artifact_root = Path(
            artifact_root or spec.root / "data/skillsbench/public-artifacts" / task
        )
        self.model_journal_dir = (
            Path(model_journal_dir or self.source.root / "data/skillsbench/private-models") / task
        )
        self.executor = (
            getattr(spec, "values", {}).get("runtime", {}).get("executor", "local-tools")
        )
        self.runner.execution_framework = self.executor
        if self.executor == "author-codex":
            self.public_inputs["environment"].update(
                execution_agent="author-codex",
                skill_directory="/app/environment/skills/current",
                execution_interface=(
                    "Native Codex terminal; read files and run scripts with shell commands."
                ),
            )

    @property
    def tool_schemas(self) -> list[dict[str, Any]]:
        if self.executor == "author-codex":
            return [
                {
                    "type": "function",
                    "function": {
                        "name": "exec_command",
                        "description": (
                            "Native Codex terminal in the task container. Read installed "
                            "Skill files and invoke their scripts through shell commands."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {"cmd": {"type": "string"}},
                            "required": ["cmd"],
                        },
                    },
                }
            ]
        return EXECUTION_TOOLS

    @property
    def allowed_read_only_tool_names(self) -> tuple[str, ...]:
        return ()

    @contextmanager
    def acquisition(self) -> Any:
        def reject(*_args: Any, **_kwargs: Any) -> Any:
            raise PermissionError("skillsbench_acquisition_has_no_simulator_or_bank_tools")

        yield SimpleNamespace(
            public_inputs=self.public_inputs, tool_schemas=[], clarify=reject, read=reject
        )

    def verifier_runner(self) -> Any:
        return self.runner

    @contextmanager
    def evolution_session(
        self,
        initial_bundle: Any,
        public_inputs: Mapping[str, Any],
        frozen_base: Any,
        *,
        journal: Any,
        workspace: Path,
    ) -> Any:
        from .container import _public_workspace
        from .core._canonical import thaw_json
        from .skillsbench_runtime import SkillsBenchRunner

        learning = SkillsBenchRunner(
            self.spec.root,
            self.task_id,
            demo=False,
            runtime="docker",
            runtime_lock_path=self.runner.runtime_lock_path,
            transport=self.runner.transport,
        )
        workspace = Path(workspace)
        identity = {
            "journal": json.loads((journal.root / "identity.json").read_text()),
            "initial_bundle_hash": initial_bundle.bundle_hash,
            "base": frozen_base.to_dict()
            if hasattr(frozen_base, "to_dict")
            else thaw_json(frozen_base),
            "public_inputs": thaw_json(public_inputs),
            "runtime_lock_hash": _hash(learning.runtime_lock_path),
        }
        with _public_workspace(
            learning,
            public_inputs,
            frozen_base,
            previous_bundle=initial_bundle,
            workspace=workspace,
            terminal_callback=learning._public_terminal,
        ) as public:
            checkpoint = workspace / "evolution-runtime.json"
            with learning.learning_episode(public, checkpoint=checkpoint, identity=identity) as (
                episode,
                state,
            ):
                yield SkillsBenchEvolutionSession(
                    self, learning, public, episode, checkpoint, state
                )

    def _model(self) -> Any:
        if self.model_factory is not None:
            return self.model_factory("execution")
        from .credentials import bearer_token_source
        from .model import GenerationConfig, OpenAICompatibleClient, SerializedChatTokenCounter

        provider, settings = self.spec.provider_settings, self.spec.values["runtime"]
        agent = settings["controls"]["agent"]
        return OpenAICompatibleClient(
            provider["api_base"],
            api_key=bearer_token_source(provider["api_key_env"]),
            config=GenerationConfig(
                model=provider["model"],
                transport=provider["transport"],
                reasoning_effort=agent["reasoning_effort"],
                max_output_tokens=agent["max_output_tokens"],
                max_input_tokens=settings["controls"]["max_input_tokens"],
            ),
            timeout_seconds=settings["request_timeout_seconds"],
            token_counter=SerializedChatTokenCounter(self.counter) if self.counter else None,
        )

    def _execute(self, bundle: Any, episode: Any) -> dict[str, Any]:
        if self.executor == "author-codex":
            return self._execute_codex(bundle, episode)
        from .journal import Journal, UnknownOperation
        from .model import ModelClientError, authentication_status, is_credential_error

        model = self._model()
        episode_id = getattr(episode, "model_episode_id", None) or uuid.uuid4().hex
        episode.model_episode_id = episode_id
        identity = {
            "task_id": self.task_id,
            "episode_id": episode_id,
            "bundle_hash": bundle.bundle_hash,
        }
        journal = Journal(self.model_journal_dir / episode_id, identity=identity)
        prompt = (self.spec.root / "prompts/execution-skillsbench.md").read_text()
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": prompt
                + "\n\n<loaded_skill>\n"
                + bundle.files["SKILL.md"]
                + "\n</loaded_skill>",
            },
            {"role": "user", "content": json.dumps(self.public_inputs, ensure_ascii=False)},
        ]
        runtime = self.spec.values["runtime"]
        controls = runtime["controls"]
        budget = controls["assistant_completion_budget"]
        used, calls, events, reason = 0, 0, [], "turn_budget_exhausted"
        termination_metadata: dict[str, Any] = {}
        started = time.monotonic()
        for turn in range(runtime.get("max_turns", 100)):
            if time.monotonic() - started >= self.runner.config["agent"]["timeout_sec"]:
                reason = "episode_timeout"
                break
            remaining = budget - used
            if remaining <= 0:
                reason = "completion_budget_exhausted"
                break
            kwargs = {
                "tools": self.tool_schemas,
                "max_output_tokens": min(remaining, controls["agent"]["max_output_tokens"]),
            }
            operation = f"execution-{turn}"
            try:
                if hasattr(model, "complete_journaled"):
                    raw = model.complete_journaled(journal, operation, identity, messages, **kwargs)
                else:
                    # Offline clients return a normalized response. Real clients seal provider
                    # bytes before parsing through complete_journaled above.
                    raw = journal.dispatch(
                        operation,
                        {"inputs": identity, "messages": messages, **kwargs},
                        lambda _kwargs=kwargs: model.complete(messages, **_kwargs),
                    )
            except (ModelClientError, UnknownOperation) as exc:
                cause: BaseException | None = exc
                seen: set[int] = set()
                while cause is not None and id(cause) not in seen:
                    seen.add(id(cause))
                    if isinstance(cause, ModelClientError):
                        break
                    cause = cause.__cause__ or cause.__context__
                if (
                    not isinstance(cause, ModelClientError)
                    or cause.code != "input_token_budget_exceeded"
                    or is_credential_error(exc)
                    or authentication_status(exc) is not None
                    or journal.status(operation) != "NOT_SENT"
                    or journal.received(operation)
                ):
                    raise
                # Admission failed before a POST. Earlier task actions are known and
                # must still be snapshotted, verified and independently graded.
                reason = "input_token_budget_exhausted"
                termination_metadata = {
                    "error_code": cause.code,
                    "input_request_status": "NOT_SENT",
                }
                details = getattr(cause, "details", {})
                if isinstance(details, Mapping):
                    for key in (
                        "observed_input_tokens",
                        "max_input_tokens",
                    ):
                        value = details.get(key)
                        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                            termination_metadata[key] = value
                break
            used += raw.get("usage", {}).get("completion_tokens", 0)
            if raw.get("finish_reason", "stop") not in {"stop", "tool_calls"}:
                reason = "model_output_incomplete"
                break
            messages.append(raw)
            if raw.get("content"):
                # Assistant text can quote the loaded package or private tool IO.
                # Keep it in this executor session; verification uses artifacts.
                events.append({"type": "message_status", "role": "assistant", "status": "returned"})
            tool_calls = raw.get("tool_calls") or []
            if not tool_calls:
                reason = "agent_finished"
                break
            for call in tool_calls:
                if calls >= runtime.get("max_task_tool_calls", 800):
                    reason = "tool_budget_exhausted"
                    break
                calls += 1
                name = call["function"]["name"]
                try:
                    arguments = json.loads(call["function"]["arguments"])
                    if name == "read_skill_file":
                        result = {"content": episode.read_skill_file(**arguments)}
                    elif name == "run_skill_script":
                        result = episode.run_skill_script(**arguments).to_dict()
                    elif name == "run_terminal_command":
                        result = self.runner.terminal(episode, **arguments).to_dict()
                    else:
                        raise PermissionError("unsupported_execution_tool")
                    event = {
                        "type": "tool_status",
                        "name": name,
                        "exit_code": result.get("exit_code"),
                        "failure": result.get("failure"),
                        "status": "returned",
                    }
                except (OSError, ValueError, TypeError, PermissionError) as exc:
                    if (
                        isinstance(exc, OSError)
                        and not isinstance(exc, PermissionError)
                        and name != "read_skill_file"
                    ):
                        # A transport failure cannot establish whether a terminal/script
                        # executed. Let the enclosing operation remain UNKNOWN.
                        raise
                    result = {"failure": type(exc).__name__}
                    event = {
                        "type": "tool_status",
                        "name": name,
                        "status": "failed",
                        "failure": type(exc).__name__,
                    }
                # Source reads and raw terminal/script IO remain private to the execution session.
                events.append(event)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
            if reason == "tool_budget_exhausted":
                break
        return {
            "benchmark": "skillsbench",
            "task_id": self.task_id,
            "events": events,
            "termination_reason": reason,
            **({"termination_metadata": termination_metadata} if termination_metadata else {}),
            "assistant_completion_tokens": used,
            "tool_calls": calls,
        }

    @contextmanager
    def _execution_episode(self, bundle: Any, *, evaluation: bool = False) -> Any:
        if self.executor != "author-codex":
            if bundle is None:
                raise ValueError("no_skill_requires_author_codex")
            with self.runner.episode(bundle) as episode:
                episode.model_episode_id = uuid.uuid4().hex
                episode.grader_evidence_dir = (
                    self.model_journal_dir / episode.model_episode_id / "official-grader"
                )
                episode.grader_identity = {
                    "episode_id": episode.model_episode_id,
                    "bundle_hash": bundle.bundle_hash,
                    "evaluation": evaluation,
                }
                yield episode
            return
        from .codex_provider import open_provider
        from .codex_runtime import codex_identity
        from .retrieval import text_counter

        settings = self.spec.values["runtime"]
        installed = codex_identity(settings["codex"])
        self._codex_binary = Path(installed.pop("binary"))
        companion = installed.pop("code_mode_host_binary", None)
        self._codex_code_mode_host = Path(companion) if companion is not None else None
        self.runner.codex_skill_mode = bundle is not None
        self.runner.agent_timeout_seconds = settings["codex"][
            "evaluation_timeout_seconds" if evaluation else "evolution_timeout_seconds"
        ]
        self._executor_identity = {
            **installed,
            "model": self.spec.provider_settings["model"],
            "cli_model": self.spec.provider_settings["model"].removeprefix("openai."),
            "controls": settings["controls"],
            "episode_timeout_seconds": self.runner.agent_timeout_seconds,
            "provider_request_timeout_seconds": settings["request_timeout_seconds"],
            "max_model_requests": settings["max_turns"],
            "task_runtime_lock_sha256": _hash(self.runner.runtime_lock_path),
        }
        episode_id = uuid.uuid4().hex
        self._codex_logs = self.model_journal_dir / episode_id / "codex"
        with tempfile.TemporaryDirectory(prefix="sb-provider-") as temporary:
            directory = Path(temporary) / "gateway"
            with open_provider(
                directory,
                self.spec.provider_settings,
                settings["controls"],
                self.model_journal_dir / episode_id / "provider",
                {
                    "task_id": self.task_id,
                    "episode_id": episode_id,
                    "bundle_hash": bundle.bundle_hash if bundle else None,
                    "executor": self._executor_identity,
                },
                token_counter=self.counter or text_counter(self.spec),
                timeout_seconds=settings["request_timeout_seconds"],
                max_requests=settings["max_turns"],
            ) as gateway:
                self._codex_gateway = gateway
                self.runner.provider_directory = directory
                try:
                    with self.runner.episode(bundle) as episode:
                        episode.model_episode_id = episode_id
                        episode.grader_evidence_dir = (
                            self.model_journal_dir / episode_id / "official-grader"
                        )
                        episode.grader_identity = {
                            "episode_id": episode_id,
                            "bundle_hash": bundle.bundle_hash if bundle else None,
                            "evaluation": evaluation,
                        }
                        yield episode
                finally:
                    self.runner.provider_directory = None
                    self._codex_gateway = None

    def _execute_codex(self, bundle: Any, episode: Any) -> dict[str, Any]:
        from .codex_provider import OUTPUT_TOKEN_BUDGET_STOP
        from .codex_runtime import CodexProvider, execute_codex
        from .container import ContainerUnavailable
        from .journal import UnknownOperation
        from .model import ModelClientError

        gateway = self._codex_gateway
        controls = self.spec.values["runtime"]["controls"]
        trace = execute_codex(
            self.runner,
            episode,
            instruction=self.public_inputs["opening"],
            logs_dir=self._codex_logs,
            bundle=bundle,
            provider=CodexProvider(
                model=self.spec.provider_settings["model"].removeprefix("openai."),
                base_url=gateway.base_url,
                binary=self._codex_binary,
                code_mode_host=getattr(self, "_codex_code_mode_host", None),
                reasoning_effort=controls["agent"]["reasoning_effort"],
                input_token_limit=controls["max_input_tokens"],
                relay_command=(
                    self.runner.public_python,
                    "/run/skill-provider/relay.py",
                    "/run/skill-provider/provider.sock",
                    "18765",
                ),
            ),
        )
        gateway.close_public()
        statistics = gateway.statistics
        atomic_json(self._codex_logs.parent / "provider-statistics.json", statistics)
        if statistics.get("authentication_status"):
            raise ModelClientError(
                "http_error",
                "Codex provider authentication failed",
                status=statistics["authentication_status"],
            )
        if statistics.get("unknown_operation"):
            raise UnknownOperation("codex_provider_response_unknown")
        budget_stops = {
            "provider_completion_budget_exhausted",
            "provider_input_bytes_exceeded",
            "input_token_budget_exceeded",
        }
        terminal = statistics.get("terminal_stop")
        if (
            isinstance(terminal, dict)
            and terminal.get("kind") == "budget"
            and terminal.get("reason") == "max_output_tokens"
            and terminal.get("response_status") == "incomplete"
        ):
            budget_stops.add(OUTPUT_TOKEN_BUDGET_STOP)
        if statistics.get("halted") and statistics.get("failure_code") not in budget_stops:
            raise ModelClientError(
                statistics.get("failure_code") or "codex_provider_failed",
                "Codex provider did not complete execution",
            )
        if trace["termination_reason"] == "codex_runtime_error" or not statistics["requests"]:
            raise ContainerUnavailable("codex_execution_not_ready")
        if statistics.get("halted"):
            trace["termination_reason"] = statistics["failure_code"]
        elif trace["termination_reason"] == "codex_error":
            raise ContainerUnavailable("codex_cli_execution_failed")
        return {
            "benchmark": "skillsbench",
            "task_id": self.task_id,
            "termination_reason": trace["termination_reason"],
            "events": [{"type": "execution_status", "status": trace["termination_reason"]}],
            "executor": self._executor_identity,
            "assistant_completion_tokens": statistics["output_tokens"],
            "provider_requests": statistics["requests"],
        }

    def _snapshot(self, episode: Any) -> dict[str, Any]:
        if not self.runner.use_bwrap:
            with self.runner.snapshot_workspace() as mounts:
                return self._seal_public_workspace(mounts)
        return self._seal_public_workspace(
            {getattr(self.runner, "workspace_directory", "/root"): episode.work}
        )

    def _seal_public_workspace(
        self, mounts: Mapping[str, Path], *, excluded_roots: Sequence[str] = ()
    ) -> dict[str, Any]:
        path = self.artifact_root / uuid.uuid4().hex
        files_root = path / "files"
        files_root.mkdir(parents=True)
        files = []
        links = []
        directories = []
        excluded: list[dict[str, str]] = []
        permissions_repaired = False
        selected: dict[str, tuple[Path, Path]] = {}
        for mount, directory in mounts.items():
            (files_root / mount.lstrip("/")).mkdir(parents=True, exist_ok=True)
            directories.append(mount.lstrip("/"))
            for original in directory.rglob("*"):
                relative = mount.lstrip("/") + "/" + original.relative_to(directory).as_posix()
                if any(
                    "/" + relative == root or ("/" + relative).startswith(root.rstrip("/") + "/")
                    for root in excluded_roots
                ):
                    continue
                parts = original.relative_to(directory).parts
                if any(p in {"skills", ".claude", ".codex", ".evolution", ".venv"} for p in parts):
                    continue
                if relative.startswith(("root/verifier/", "logs/verifier/")):
                    continue
                selected[relative] = (original, directory)
        for relative, (original, directory) in sorted(selected.items()):
            if original.is_symlink():
                target = os.readlink(original)
                if not _public_link_target(relative, target, tuple(mounts)):
                    raise ValueError("skillsbench_public_artifact_not_regular")
                destination = files_root / _safe_path(relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.symlink_to(target)
                links.append({"path": relative, "target": target})
                continue
            if not original.resolve().is_relative_to(directory.resolve()) or any(
                parent.is_symlink() for parent in original.parents if parent != directory
            ):
                # A path that resolves outside its mount is a host-escape attempt.
                raise ValueError("skillsbench_public_artifact_not_regular")
            if original.is_dir() and not original.is_symlink():
                (files_root / _safe_path(relative)).mkdir(parents=True, exist_ok=True)
                directories.append(relative)
                continue
            if original.is_symlink() or not original.is_file():
                # The executor may leave a symlink/directory/special file at a declared
                # artifact path. Such a path is not a public artifact; it is excluded and
                # recorded instead of failing the whole rollout as unknown.
                excluded.append({"path": relative, "reason": "not_regular_file"})
                continue
            destination = files_root / _safe_path(relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copyfile(original, destination)
            except PermissionError:
                # The executor runs as root inside the container and may leave its
                # artifacts unreadable for the host user; open them up once via a
                # throwaway container (the episode is over, so this changes no result).
                if permissions_repaired:
                    raise
                if self.runner.runtime == "workspace":
                    raise PermissionError(
                        "skillsbench_workspace_public_artifact_unreadable"
                    ) from None
                for mount_directory in mounts.values():
                    _open_permissions(mount_directory)
                permissions_repaired = True
                shutil.copyfile(original, destination)
            destination.chmod(0o555 if original.stat().st_mode & 0o111 else 0o444)
            files.append(
                {
                    "path": relative,
                    "sandbox_path": "/" + relative,
                    "sha256": _hash(destination),
                    "bytes": destination.stat().st_size,
                    "mode": destination.stat().st_mode & 0o777,
                }
            )
        snapshot_hash = _json_hash(
            {"files": files, "directories": sorted(directories), "symlinks": links}
        )
        atomic_json(
            path / "snapshot.json",
            {
                "files": files,
                "directories": sorted(directories),
                "symlinks": links,
                "excluded": excluded,
                "snapshot_hash": snapshot_hash,
            },
        )
        return {
            "public_artifacts_dir": str(files_root),
            "public_artifacts_hash": snapshot_hash,
            "public_artifacts": files[:128],
            "public_artifact_count": len(files),
            "public_artifact_manifest_truncated": len(files) > 128,
            "public_artifacts_excluded": excluded,
        }

    def rollout(self, bundle: Any) -> dict[str, Any]:
        with self._execution_episode(bundle) as episode:
            trace = self._execute(bundle, episode)
            return {**trace, **self._snapshot(episode)}

    def oracle(self, bundle: Any) -> bool:
        with self._execution_episode(bundle) as episode:
            self._execute(bundle, episode)
            self._snapshot(episode)
            self.runner.close_public(episode)
            result = self.runner.grade(episode)
        if result["status"] != "MEASURED":
            from .evolution import OracleUnavailable

            raise OracleUnavailable("skillsbench_oracle_not_measured")
        return result["utility"] is True

    def evaluate(self, bundle: Any) -> dict[str, Any]:
        return self._evaluate(bundle)

    def evaluate_no_skill(self) -> dict[str, Any]:
        if self.executor != "author-codex":
            raise ValueError("no_skill_requires_author_codex")
        return self._evaluate(None)

    def _evaluate(self, bundle: Any) -> dict[str, Any]:
        with self._execution_episode(bundle, evaluation=True) as episode:
            trace = self._execute(bundle, episode)
            self._snapshot(episode)
            self.runner.close_public(episode)
            result = self.runner.grade(episode)
        return {
            **result,
            "benchmark": "skillsbench",
            "asr": None,
            "asr_status": "NOT_APPLICABLE",
            "completion_steps": None,
            "execution_termination_reason": trace.get("termination_reason"),
            "executor": trace.get("executor"),
            **(
                {"execution_termination_metadata": trace["termination_metadata"]}
                if trace.get("termination_metadata")
                else {}
            ),
        }


class SkillsBenchEvolutionSession:
    """One Generator's live task state; only explicit submissions become evidence."""

    tool_schemas: tuple[Any, ...] = ()

    def __init__(
        self,
        adapter: Any,
        runner: Any,
        public: Any,
        episode: Any,
        checkpoint: Path,
        state: dict[str, Any],
    ):
        self.adapter, self.runner, self.public, self.episode = adapter, runner, public, episode
        self.checkpoint, self.state = checkpoint, state

    def _save(self) -> None:
        atomic_json(self.checkpoint, self.state)

    def files(self) -> dict[str, str]:
        return self.public.files()

    def snapshot(self) -> dict[str, Any]:
        from .container import _tree_manifest
        from .core._canonical import canonical_json_sha256

        files = self.files()
        return {
            "files": files,
            "workspace_hash": canonical_json_sha256(
                {
                    "fixed_inputs": _tree_manifest(self.public.package),
                    "candidate": files,
                    "execution_id": self.state["execution_id"],
                }
            ),
        }

    def begin_attempt(self, parent: Any, initial: bool, *, operation_id: str) -> dict[str, Any]:
        attempt = {
            "operation_id": operation_id,
            "parent_hash": parent.bundle_hash,
            "initial": initial,
        }
        previous = self.state.get("attempt")
        if (
            previous
            and previous["operation_id"] == operation_id
            and previous["status"] != "PREPARING"
        ):
            if any(previous[name] != value for name, value in attempt.items()):
                raise ValueError("skillsbench_evolution_attempt_identity_differs")
            return {
                "state": {
                    "execution_id": self.state["execution_id"],
                    "execution_count": 1,
                    "operation_cursor": self.state["operation_cursor"],
                }
            }
        self.state["attempt"] = {**attempt, "status": "PREPARING"}
        self._save()
        reset = self.runner._exec(
            ["/bin/sh", "-c", "find /work/candidate -mindepth 1 -depth -delete"], public=True
        )
        if reset.returncode or reset.failure:
            raise RuntimeError("skillsbench_evolution_candidate_reset_failed")
        for relative, content in parent.files.items():
            path = self.public.target / _safe_path(relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            path.chmod(0o666)
            for directory in path.parents:
                if directory == self.public.work:
                    break
                directory.chmod(0o777)
        self.state["attempt"] = {**attempt, "status": "READY"}
        self._save()
        return {
            "state": {
                "execution_id": self.state["execution_id"],
                "execution_count": 1,
                "operation_cursor": self.state["operation_cursor"],
            }
        }

    def terminal(self, command: str) -> Any:
        if self.state.get("attempt", {}).get("status") != "READY":
            raise PermissionError("skillsbench_evolution_attempt_not_open")
        result = self.runner.terminal(self.episode, command)
        self.state["operation_cursor"] += 1
        self.state["events"].append(
            {
                "kind": "tool",
                "name": "terminal",
                "exit_code": result.exit_code,
                "failure": result.failure,
                "operation_cursor": self.state["operation_cursor"],
            }
        )
        self._save()
        return result

    def execute_tool(self, name: str, args: Mapping[str, Any], operation_id: str) -> Any:
        raise ValueError("skillsbench_evolution_has_no_additional_tools")

    def record_tool_result(self, operation_id: str, result: Any) -> str:
        from .core._canonical import canonical_json_sha256, thaw_json

        path = (
            self.public.work
            / "observations"
            / "tools"
            / (canonical_json_sha256(operation_id) + ".json")
        )
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            raise ValueError("unsafe_evolution_tool_result_path")
        value = thaw_json(result)
        if path.exists():
            if json.loads(path.read_text()) != value:
                raise ValueError("evolution_tool_result_changed")
        else:
            atomic_json(path, value)
            path.chmod(0o444)
            for parent in path.parents:
                if parent == self.public.work:
                    break
                parent.chmod(0o755)
        return "/work/observations/tools/" + path.name

    def submit(self, parent_bundle: Any, *, initial: bool = False, operation_id: str) -> Any:
        from .artifacts import EvolutionSubmission, SkillBundle
        from .core._canonical import thaw_json

        previous = self.state.get("submission")
        if previous and previous["operation_id"] == operation_id:
            if (
                previous["parent_hash"] != parent_bundle.bundle_hash
                or previous["initial"] != initial
            ):
                raise ValueError("skillsbench_evolution_submission_identity_differs")
            submission = EvolutionSubmission.from_dict(previous["value"])
            self.runner._public_artifacts(thaw_json(submission.public_trace))
            return submission
        attempt = self.state.get("attempt", {})
        if (
            attempt.get("status") != "READY"
            or attempt.get("parent_hash") != parent_bundle.bundle_hash
            or attempt.get("initial") != initial
        ):
            raise ValueError("skillsbench_evolution_submission_phase_differs")
        files = self.files()
        if initial and files != dict(parent_bundle.files):
            raise ValueError("initial_execution_changed_sealed_skill")
        bundle = (
            parent_bundle if initial else SkillBundle(files, parent_hash=parent_bundle.bundle_hash)
        )
        with self.runner.snapshot_workspace() as mounts:
            trace = {
                "task_id": self.adapter.task_id,
                "events": list(self.state["events"]),
                "termination_reason": "generator_submitted",
                "executor": {"framework": "generator-direct"},
                **self.adapter._seal_public_workspace(
                    mounts, excluded_roots=_EVOLUTION_PRIVATE_ROOTS
                ),
            }
        if self.files() != files:
            raise ValueError("candidate_changed_during_submission")
        submission = EvolutionSubmission(
            bundle, trace, self.state["execution_id"], self.state["operation_cursor"], initial
        )
        self.state["submission"] = {
            "operation_id": operation_id,
            "parent_hash": parent_bundle.bundle_hash,
            "initial": initial,
            "value": submission.to_dict(),
        }
        self.state["attempt"]["status"] = "SUBMITTED"
        self._save()
        return submission


def skillsbench_preflight(
    spec: Any,
    *,
    demo: bool,
    task_ids: Any,
    runtime: str | None = None,
) -> dict[str, Any]:
    from .skillsbench_runtime import SkillsBenchRunner

    checks = []
    if spec.values["runtime"].get("executor") == "author-codex":
        try:
            if runtime not in {None, "docker"} or demo:
                raise ValueError("author_codex_requires_docker")
            from .codex_runtime import codex_identity

            identity = codex_identity(spec.values["runtime"]["codex"])
            checks.append({"name": "author_codex", "ok": True, "detail": identity})
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            checks.append({"name": "author_codex", "ok": False, "detail": str(exc)})
    try:
        source = SkillsBenchSource(spec.root)
        source.validate()
        checks.append(
            {
                "name": "skillsbench_source",
                "ok": True,
                "detail": {
                    "task_count": TASK_COUNT,
                    "manifest_hash": source.manifest["manifest_hash"],
                },
            }
        )
    except (OSError, ValueError, RuntimeError) as exc:
        return {
            "ready": False,
            "checks": [{"name": "skillsbench_source", "ok": False, "detail": str(exc)}],
        }
    try:
        manifest = validate_pool(spec.root, source)
        checks.append(
            {
                "name": "skillsbench_public_pool",
                "ok": True,
                "detail": {"pages": len(manifest["pages"]), "corpus_hash": manifest["corpus_hash"]},
            }
        )
        cache = spec.root / "data/skillsbench/dense" / manifest["corpus_hash"]
        dense = json.loads((cache / "manifest.json").read_text())
        vector = cache / "vectors.f32"
        contract = dense["contract"]
        expected = sorted(manifest["pages"], key=lambda x: x["page_id"])
        descriptors = [{k: p[k] for k in ("page_id", "content_sha256")} for p in contract["pages"]]
        if (
            descriptors != [{k: p[k] for k in ("page_id", "content_sha256")} for p in expected]
            or contract["model_id"] != spec.values["embedding"]["model"]
            or contract["model_revision"] != spec.values["embedding"]["revision"]
        ):
            raise ValueError("skillsbench_dense_source_contract_invalid")
        from .core._canonical import canonical_json_sha256

        unsigned = {k: v for k, v in dense.items() if k != "manifest_payload_sha256"}
        if (
            dense["manifest_payload_sha256"] != canonical_json_sha256(unsigned)
            or dense["vectors"]["shape"]
            != [len(manifest["pages"]), spec.values["embedding"]["dimension"]]
            or dense["vectors"]["sha256"] != _hash(vector)
        ):
            raise ValueError("skillsbench_dense_cache_invalid")
        checks.append(
            {
                "name": "skillsbench_dense_index",
                "ok": True,
                "detail": {"vector_bytes": vector.stat().st_size},
            }
        )
    except (OSError, ValueError, KeyError) as exc:
        checks.append(
            {"name": "skillsbench_public_pool_and_index", "ok": False, "detail": str(exc)}
        )
    for task in task_ids or (("3d-scan-calc",) if demo else source.manifest["tasks"]):
        try:
            result = SkillsBenchRunner(
                spec.root,
                task,
                demo=demo,
                runtime=runtime,
                runtime_lock_path=spec.root / spec.values["source"]["runtime_lock"],
            ).preflight(
                validate_source=False,
                **(
                    {"author_codex": spec.values["runtime"]["codex"]}
                    if spec.values["runtime"].get("executor") == "author-codex"
                    else {}
                ),
            )
        except (OSError, ValueError, RuntimeError) as exc:
            result = {"ready": False, "error": str(exc)}
        checks.append(
            {"name": f"skillsbench_environment:{task}", "ok": result["ready"], "detail": result}
        )
    return {"ready": all(c["ok"] for c in checks), "checks": checks}
