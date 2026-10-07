"""Shared fixtures: retry back-off never sleeps inside the offline test suite."""

from __future__ import annotations

import pytest
from tau_skill_evolution import model


@pytest.fixture(autouse=True)
def _no_retry_sleep(monkeypatch):
    monkeypatch.setattr(model, "_sleep", lambda _delay: None)
