"""Terminal experiment statuses with fixed denominator semantics."""

from __future__ import annotations

from enum import Enum


class RunStatus(str, Enum):
    SUCCESS = "SUCCESS"
    DEFERRED = "DEFERRED"
    INVALID = "INVALID"
    BEHAVIORAL_FAIL = "BEHAVIORAL_FAIL"
    NOT_RUN_UPSTREAM = "NOT_RUN_UPSTREAM"

    @property
    def attempted(self) -> bool:
        """Whether this cell is a valid behavioral trial in a denominator."""

        return self in {self.SUCCESS, self.BEHAVIORAL_FAIL}

    @property
    def infrastructure_failure(self) -> bool:
        return self is self.INVALID

    @property
    def ran(self) -> bool:
        return self in {self.SUCCESS, self.BEHAVIORAL_FAIL, self.INVALID}


def parse_run_status(value: str | RunStatus) -> RunStatus:
    if isinstance(value, RunStatus):
        return value
    if not isinstance(value, str):
        raise TypeError("run status must be a string or RunStatus")
    return RunStatus(value)
