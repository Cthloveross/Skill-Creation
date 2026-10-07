"""Pure aggregation routines for GitHub monthly activity reports."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

UNKNOWN_AUTHOR = "<unknown>"


def parse_instant(value: str) -> datetime:
    """Parse a GitHub ISO-8601 instant as an aware UTC datetime."""
    if not isinstance(value, str) or not value:
        raise ValueError("missing timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    result = datetime.fromisoformat(normalized)
    if result.tzinfo is None:
        raise ValueError("timestamp has no timezone")
    return result.astimezone(timezone.utc)


def in_window(value: str, start: datetime, end: datetime) -> bool:
    instant = parse_instant(value)
    return start <= instant < end


def is_bug(labels: list[str], token: str = "bug") -> bool:
    needle = token.casefold()
    return any(isinstance(name, str) and needle in name.casefold() for name in labels)


def _author_login(node: dict[str, Any]) -> str:
    author = node.get("author")
    if isinstance(author, dict) and isinstance(author.get("login"), str) and author["login"]:
        return author["login"]
    return UNKNOWN_AUTHOR


def _duration_days(created_at: str, merged_at: str) -> Decimal:
    delta = parse_instant(merged_at) - parse_instant(created_at)
    seconds = Decimal(delta.days * 86400 + delta.seconds) + Decimal(delta.microseconds) / Decimal(1000000)
    return seconds / Decimal(86400)


def aggregate(
    pull_requests: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    """Aggregate already-fetched GraphQL nodes after enforcing cohort boundaries."""
    cohort_prs = [node for node in pull_requests if in_window(node["createdAt"], start, end)]
    cohort_issues = [node for node in issues if in_window(node["createdAt"], start, end)]

    merged_prs = [node for node in cohort_prs if node.get("state") == "MERGED"]
    closed_prs = [node for node in cohort_prs if node.get("state") == "CLOSED"]
    durations: list[Decimal] = []
    for node in merged_prs:
        merged_at = node.get("mergedAt")
        if isinstance(merged_at, str) and merged_at:
            durations.append(_duration_days(node["createdAt"], merged_at))

    if durations:
        average = (sum(durations) / Decimal(len(durations))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        average_days = float(average)
    else:
        average_days = 0.0

    authors = Counter(_author_login(node) for node in cohort_prs)
    top_contributor = min(authors, key=lambda login: (-authors[login], login)) if authors else UNKNOWN_AUTHOR

    bug_issues = [node for node in cohort_issues if is_bug(node.get("labelNames", []))]
    resolved_bugs = [
        node for node in bug_issues
        if isinstance(node.get("closedAt"), str) and node["closedAt"] and in_window(node["closedAt"], start, end)
    ]

    return {
        "pr": {
            "total": len(cohort_prs),
            "merged": len(merged_prs),
            "closed": len(closed_prs),
            "avg_merge_days": average_days,
            "top_contributor": top_contributor,
        },
        "issue": {
            "total": len(cohort_issues),
            "bug": len(bug_issues),
            "resolved_bugs": len(resolved_bugs),
        },
    }


def validate_report(report: dict[str, Any]) -> None:
    """Raise ValueError unless report conforms exactly to the public artifact schema."""
    expected = {
        "pr": {
            "total": int,
            "merged": int,
            "closed": int,
            "avg_merge_days": float,
            "top_contributor": str,
        },
        "issue": {"total": int, "bug": int, "resolved_bugs": int},
    }
    if set(report) != set(expected):
        raise ValueError("report top-level keys do not match required schema")
    for section, fields in expected.items():
        value = report.get(section)
        if not isinstance(value, dict) or set(value) != set(fields):
            raise ValueError("report section keys do not match required schema: " + section)
        for name, expected_type in fields.items():
            actual = value[name]
            # bool is a subclass of int but is not an acceptable count.
            if not isinstance(actual, expected_type) or (expected_type is int and isinstance(actual, bool)):
                raise ValueError("invalid type for " + section + "." + name)
            if expected_type is int and actual < 0:
                raise ValueError("negative count for " + section + "." + name)
