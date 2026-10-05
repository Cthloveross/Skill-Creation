#!/usr/bin/env python3
"""Aggregate GitHub PR and issue records into a monthly report.

Input: JSON object on stdin. Required: start, end, output_path, and exactly one
of direct array or *_path input for each of pull_requests and issues.
Output: JSON status object on stdout; report is atomically written to output_path.
"""
import json
import math
import os
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


class InputError(ValueError):
    pass


def fail(message):
    raise InputError(message)


def get(row, *names, default=None):
    for name in names:
        if name in row:
            return row[name]
    return default


def need(row, description, *names):
    value = get(row, *names)
    if value is None:
        fail(f"missing {description}; accepted fields: {', '.join(names)}")
    return value


def present(row, description, *names):
    for name in names:
        if name in row:
            return row[name]
    fail(f"missing {description} field; accepted fields: {', '.join(names)}")


def timestamp(value, description):
    if not isinstance(value, str) or not value:
        fail(f"{description} must be a nonempty ISO-8601 timestamp")
    try:
        result = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as exc:
        fail(f"invalid {description}: {exc}")
    if result.tzinfo is None or result.utcoffset() is None:
        fail(f"{description} must include a timezone")
    return result.astimezone(timezone.utc)


def record_id(row, kind):
    value = get(row, "id", "node_id", "nodeId", "number")
    if value is None or isinstance(value, (dict, list, bool)):
        fail(f"{kind} lacks stable id, node_id, nodeId, or number")
    return str(value)


def collection(config, direct, path_key):
    has_direct, has_path = direct in config, path_key in config
    if has_direct == has_path:
        fail(f"supply exactly one of {direct} and {path_key}")
    if has_direct:
        rows = config[direct]
    else:
        path = config[path_key]
        if not isinstance(path, str) or not path:
            fail(f"{path_key} must be a nonempty path")
        try:
            with open(path, encoding="utf-8") as handle:
                rows = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            fail(f"cannot load {path_key}: {exc}")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        fail(f"{direct} must be an array of objects")
    return rows


def unique(rows, kind):
    seen, result = set(), []
    for row in rows:
        key = record_id(row, kind)
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result


def labels(row):
    value = get(row, "labels", default=[])
    if value is None:
        return []
    if isinstance(value, dict):
        if isinstance(value.get("nodes"), list):
            value = value["nodes"]
        elif isinstance(value.get("edges"), list):
            value = [edge.get("node") for edge in value["edges"] if isinstance(edge, dict)]
        else:
            fail("labels object must contain nodes or edges")
    if not isinstance(value, list):
        fail("labels must be an array or GraphQL connection")
    result = []
    for label in value:
        if isinstance(label, str):
            result.append(label)
        elif isinstance(label, dict) and isinstance(label.get("name"), str):
            result.append(label["name"])
        else:
            fail("every label must be a string or object with string name")
    return result


def author(row):
    value = get(row, "author", "user")
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    if isinstance(value, dict):
        login = value.get("login")
        if login is None:
            return None
        if not isinstance(login, str):
            fail("author login must be a string")
        return login or None
    fail("author/user must be a string, object, or null")


def write_json(path_value, value):
    if not isinstance(path_value, str) or not path_value:
        fail("output path must be a nonempty string")
    destination = Path(path_value)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=".report-", suffix=".tmp", dir=str(destination.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except OSError as exc:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass
        fail(f"cannot write {destination}: {exc}")


def validate(report):
    if not isinstance(report, dict) or set(report) != {"pr", "issue"}:
        fail("report must contain exactly pr and issue")
    pr, issue = report["pr"], report["issue"]
    if not isinstance(pr, dict) or set(pr) != {"total", "merged", "closed", "avg_merge_days", "top_contributor"}:
        fail("invalid pr report keys")
    if not isinstance(issue, dict) or set(issue) != {"total", "bug", "resolved_bugs"}:
        fail("invalid issue report keys")
    for group, keys in ((pr, ("total", "merged", "closed")), (issue, ("total", "bug", "resolved_bugs"))):
        for key in keys:
            if isinstance(group[key], bool) or not isinstance(group[key], int) or group[key] < 0:
                fail(f"{key} must be a nonnegative integer")
    if pr["merged"] > pr["total"] or pr["closed"] > pr["total"]:
        fail("PR status count exceeds total")
    if issue["bug"] > issue["total"] or issue["resolved_bugs"] > issue["bug"]:
        fail("issue status count exceeds cohort")
    average = pr["avg_merge_days"]
    if isinstance(average, bool) or not isinstance(average, float) or not math.isfinite(average) or average < 0 or round(average, 1) != average:
        fail("avg_merge_days must be a finite nonnegative float rounded to one decimal")
    if not isinstance(pr["top_contributor"], str) or not pr["top_contributor"].strip():
        fail("top_contributor must be a nonempty string")


def build(config):
    if not isinstance(config, dict):
        fail("stdin must be a JSON object")
    start, end = timestamp(need(config, "start", "start"), "start"), timestamp(need(config, "end", "end"), "end")
    if end <= start:
        fail("end must be later than start")
    prs = unique(collection(config, "pull_requests", "pull_requests_path"), "pull request")
    raw_issues = unique(collection(config, "issues", "issues_path"), "issue")
    issues = [row for row in raw_issues if "pull_request" not in row and "pullRequest" not in row]

    authors, durations, pr_audit = Counter(), [], []
    merged_count = closed_count = total_pr = 0
    for row in prs:
        rid = record_id(row, "pull request")
        created = timestamp(need(row, "PR creation time", "createdAt", "created_at"), f"PR {rid} createdAt")
        if not start <= created < end:
            continue
        state = need(row, "PR state", "state")
        if not isinstance(state, str):
            fail(f"PR {rid} state must be a string")
        raw_merge = present(row, "PR merge timestamp", "mergedAt", "merged_at")
        merged_at = None if raw_merge is None else timestamp(raw_merge, f"PR {rid} mergedAt")
        merged = merged_at is not None or state.upper() == "MERGED"
        if merged and merged_at is None:
            fail(f"merged PR {rid} lacks merge timestamp")
        closed = state.upper() == "CLOSED" and not merged
        if merged:
            elapsed_us = int((merged_at - created).total_seconds() * 1000000)
            if elapsed_us < 0:
                fail(f"PR {rid} was merged before creation")
            durations.append(elapsed_us)
            merged_count += 1
        closed_count += int(closed)
        login = author(row)
        if login:
            authors[login] += 1
        total_pr += 1
        pr_audit.append({"id": rid, "created_at": created.isoformat(), "state": state, "merged_at": None if merged_at is None else merged_at.isoformat(), "merged": merged, "closed_unmerged": closed, "author": login})

    total_issue = bug_count = resolved_count = 0
    issue_audit = []
    for row in issues:
        rid = record_id(row, "issue")
        created = timestamp(need(row, "issue creation time", "createdAt", "created_at"), f"issue {rid} createdAt")
        if not start <= created < end:
            continue
        names = labels(row)
        bug = any("bug" in name.casefold() for name in names)
        raw_closed = present(row, "issue closure timestamp", "closedAt", "closed_at")
        closed_at = None if raw_closed is None else timestamp(raw_closed, f"issue {rid} closedAt")
        resolved = bug and closed_at is not None and start <= closed_at < end
        total_issue += 1
        bug_count += int(bug)
        resolved_count += int(resolved)
        issue_audit.append({"id": rid, "created_at": created.isoformat(), "labels": names, "bug": bug, "closed_at": None if closed_at is None else closed_at.isoformat(), "resolved_bug_in_window": resolved})

    if not authors:
        fail("no attributable PR author in cohort; cannot produce top_contributor")
    average = 0.0
    if durations:
        mean = Decimal(sum(durations)) / Decimal(len(durations)) / Decimal(86400000000)
        average = float(mean.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    top = min(authors, key=lambda login: (-authors[login], login.casefold(), login))
    report = {"pr": {"total": total_pr, "merged": merged_count, "closed": closed_count, "avg_merge_days": average, "top_contributor": top}, "issue": {"total": total_issue, "bug": bug_count, "resolved_bugs": resolved_count}}
    validate(report)
    return report, {"pull_requests": pr_audit, "issues": issue_audit}


def main():
    try:
        config = json.load(sys.stdin)
        report, audit = build(config)
        output = need(config, "output_path", "output_path")
        write_json(output, report)
        if config.get("audit_path") is not None:
            write_json(config["audit_path"], audit)
        print(json.dumps({"output_path": output, "report": report}, ensure_ascii=False, allow_nan=False))
    except (InputError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(2)


if __name__ == "__main__":
    main()
