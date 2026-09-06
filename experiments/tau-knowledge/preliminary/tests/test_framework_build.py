import pytest

from r2sp_tau_knowledge.batch_runtime import (
    _DEDICATED_BUILD_FILES,
    _DEDICATED_BUILD_VERSION,
    _check_framework_build,
)
from r2sp_tau_knowledge.batch_services import LiveInfrastructureError


def test_official_development_image_requires_exact_architecture_source_hashes():
    assert (
        _check_framework_build(
            _DEDICATED_BUILD_VERSION,
            flash=True,
            development_files=dict(_DEDICATED_BUILD_FILES),
        )
        == "pinned-dedicated-development-build"
    )
    for values in (None, {}, {**_DEDICATED_BUILD_FILES, "unexpected.py": "a" * 64}):
        with pytest.raises(LiveInfrastructureError):
            _check_framework_build(_DEDICATED_BUILD_VERSION, flash=True, development_files=values)


@pytest.mark.parametrize("version", ["0.28.0", "0.29.0rc1", "0.1.dev20074+gunknown"])
def test_unsupported_builds_are_not_treated_as_qualified(version):
    with pytest.raises(LiveInfrastructureError):
        _check_framework_build(version, flash=True, development_files=dict(_DEDICATED_BUILD_FILES))


def test_release_minimum_depends_on_selected_model():
    assert _check_framework_build("0.29.0", flash=True) == "release-version"
    assert _check_framework_build("0.28.0", flash=False) == "release-version"
