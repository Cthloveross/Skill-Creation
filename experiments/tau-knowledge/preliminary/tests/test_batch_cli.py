from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = EXPERIMENT_ROOT / "scripts"


@pytest.fixture
def scripts(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return {
        name: importlib.import_module(name)
        for name in ("build_source_bundle", "batch_source", "run_batch", "submit_batch")
    }


@pytest.fixture
def source_bundle(
    scripts: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[Path, dict[str, Any]]:
    root = tmp_path / "checkout"
    root.mkdir()
    (root / "module.py").write_text("VALUE = 1\n")
    builder = scripts["build_source_bundle"]
    monkeypatch.setattr(builder, "_listed_paths", lambda _root: ("module.py",))
    monkeypatch.setattr(builder, "_git", lambda _root, *_args: b"a" * 40)
    identity = builder.build(root=root, output_dir=tmp_path / "bundles", write=True)
    return root, identity


def test_bundle_is_deterministic_and_rejects_checkout_drift(
    scripts: dict[str, Any], source_bundle: tuple[Path, dict[str, Any]], tmp_path: Path
) -> None:
    root, original = source_bundle
    second = scripts["build_source_bundle"].build(
        root=root, output_dir=tmp_path / "bundles", write=False
    )
    assert original["bundle_sha256"] == second["bundle_sha256"]
    verifier = scripts["batch_source"]
    _, members = verifier.verified_bundle(Path(original["bundle_path"]), original["bundle_sha256"])
    verifier.verify_checkout(root, members)
    (root / "module.py").write_text("VALUE = 2\n")
    with pytest.raises(ValueError, match="differs"):
        verifier.verify_checkout(root, members)


def test_bundle_rejects_changed_archive(
    scripts: dict[str, Any], source_bundle: tuple[Path, dict[str, Any]]
) -> None:
    _, identity = source_bundle
    path = Path(identity["bundle_path"])
    path.chmod(0o644)
    path.write_bytes(path.read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="SHA-256"):
        scripts["batch_source"].verified_bundle(path, identity["bundle_sha256"])


def test_inventory_keeps_new_tests_and_omits_tracked_deletions(
    scripts: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    builder = scripts["build_source_bundle"]
    new_test = "experiments/tau-knowledge/preliminary/tests/test_batch.py"

    def git(_root: Path, *_args: str) -> bytes:
        if "--cached" in _args:
            return b"README.md\0docs/deleted.md\0"
        if "--deleted" in _args:
            return b"docs/deleted.md\0"
        return (new_test + "\0src/r2sp_tau_knowledge/batch.py\0").encode()

    monkeypatch.setattr(builder, "_git", git)
    paths = builder._listed_paths(tmp_path)
    assert new_test in paths
    assert "src/r2sp_tau_knowledge/batch.py" in paths
    assert "docs/deleted.md" not in paths


def test_validate_and_submission_dry_run_do_not_start_services_or_write(
    scripts: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    spec = EXPERIMENT_ROOT / "configs/generation-benign-10.example.yaml"
    assert scripts["run_batch"].main(["validate", "--phase", "create", "--spec", str(spec)]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert len(validated["spec"]["items"]) == 10
    submit = scripts["submit_batch"]
    bundle_dir = tmp_path / "not-written"
    monkeypatch.setattr(
        submit,
        "build",
        lambda **_kwargs: {
            "bundle_path": str(bundle_dir / "source.tar"),
            "bundle_sha256": "a" * 64,
            "manifest_sha256": "b" * 64,
            "source_tree_sha256": "c" * 64,
        },
    )

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("dry-run must not invoke an external command")

    monkeypatch.setattr(submit.subprocess, "check_output", forbidden)
    assert (
        submit.main(
            [
                "create",
                "--spec",
                str(spec),
                "--bundle-dir",
                str(bundle_dir),
                "--runs-root",
                str(tmp_path / "not-written-runs"),
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "DRY_RUN"
    assert result["runtime_assets"] == "NOT_CHECKED_DRY_RUN"
    assert "--export=NONE" in result["command"]
    assert not bundle_dir.exists()
    assert not (tmp_path / "not-written-runs").exists()


def test_cli_scripted_creation_and_replay(
    scripts: dict[str, Any],
    source_bundle: tuple[Path, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, identity = source_bundle
    cli = scripts["run_batch"]
    verifier = scripts["batch_source"]
    provenance, _ = verifier.verified_bundle(
        Path(identity["bundle_path"]), identity["bundle_sha256"]
    )
    monkeypatch.setattr(cli, "PROJECT_ROOT", root)
    monkeypatch.setattr(cli, "source_provenance", lambda *_args: dict(provenance))
    spec = EXPERIMENT_ROOT / "configs/generation-benign-10.example.yaml"
    assert (
        cli.main(
            [
                "create",
                "--spec",
                str(spec),
                "--runs-root",
                str(tmp_path / "runs"),
                "--scripted",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["execution_mode"] == "scripted"
    assert result["scope"] == "benign-only"
    assert cli.main(["replay", result["root"], "--complete-sha256", result["complete_sha256"]]) == 0
    replayed = json.loads(capsys.readouterr().out)
    assert replayed


def test_invalid_evaluation_source_fails_before_runtime_or_source_writes(
    scripts: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = scripts["run_batch"]

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("invalid source must fail before creating runtime provenance")

    monkeypatch.setattr(cli, "source_provenance", forbidden)
    spec = EXPERIMENT_ROOT / "configs/evaluation-benign.example.yaml"
    assert (
        cli.main(
            [
                "evaluate",
                "--spec",
                str(spec),
                "--runs-root",
                str(tmp_path / "absent"),
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().err)["status"] == "INVALID"
    assert not (tmp_path / "absent").exists()


def test_source_drift_prevents_completion_publication(
    scripts: dict[str, Any],
    source_bundle: tuple[Path, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from r2sp_tau_knowledge.batch import ScriptedBatchBackend

    root, identity = source_bundle
    cli = scripts["run_batch"]
    provenance, _ = scripts["batch_source"].verified_bundle(
        Path(identity["bundle_path"]), identity["bundle_sha256"]
    )
    monkeypatch.setattr(cli, "PROJECT_ROOT", root)
    monkeypatch.setattr(cli, "source_provenance", lambda *_args: dict(provenance))
    original_compile = ScriptedBatchBackend.compile

    def changed_compile(self: Any, **kwargs: Any) -> Any:
        result = original_compile(self, **kwargs)
        (root / "module.py").write_text("VALUE = 2\n")
        return result

    monkeypatch.setattr(ScriptedBatchBackend, "compile", changed_compile)
    spec = yaml.safe_load(
        (EXPERIMENT_ROOT / "configs/generation-benign-10.example.yaml").read_text()
    )
    spec["items"] = spec["items"][:1]
    spec_path = tmp_path / "single.yaml"
    spec_path.write_text(yaml.safe_dump(spec))
    runs = tmp_path / "runs"
    assert (
        cli.main(
            [
                "create",
                "--spec",
                str(spec_path),
                "--runs-root",
                str(runs),
                "--scripted",
            ]
        )
        == 2
    )
    assert "differs" in json.loads(capsys.readouterr().err)["reason"]
    assert not list(runs.rglob("generation-complete.json"))
