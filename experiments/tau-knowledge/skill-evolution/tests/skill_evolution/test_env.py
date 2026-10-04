import os

import pytest
from tau_skill_evolution.cli import load_env


def test_load_env_keeps_values_literal_and_existing_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
    monkeypatch.setenv("AWS_REGION", "us-east-2")
    path = tmp_path / "key.env"
    path.write_text(
        "# local credentials\nexport AWS_REGION=us-east-1\n"
        "AWS_BEARER_TOKEN_BEDROCK='$(touch forbidden);literal'\n"
    )
    load_env(path)
    assert os.environ["AWS_REGION"] == "us-east-2"
    assert os.environ["AWS_BEARER_TOKEN_BEDROCK"] == "$(touch forbidden);literal"
    assert not (tmp_path / "forbidden").exists()


def test_standalone_bearer_token_is_loaded_literally_without_rewriting(tmp_path, monkeypatch):
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
    path = tmp_path / "key.env"
    literal = "ABCD" * 20 + "/+/=="
    path.write_text(literal + "\n")
    load_env(path)
    assert os.environ["AWS_BEARER_TOKEN_BEDROCK"] == literal
    assert path.read_text() == literal + "\n"


@pytest.mark.parametrize("content", ["bare-secret", "KEY='secret", "KEY=secret another"])
def test_invalid_env_error_never_contains_credential_content(tmp_path, content):
    path = tmp_path / "key.env"
    path.write_text(content)
    with pytest.raises(ValueError) as error:
        load_env(path)
    assert "secret" not in str(error.value)
    assert "line 1" in str(error.value)
