#!/usr/bin/env python3
"""Build a validated monthly GitHub activity report from supplied JSON records.

Input stdin: object with start, end, output_path, and exactly one of
pull_requests/pull_requests_path and issues/issues_path.  Arrays contain REST
or GraphQL-style record objects.  Output stdout: {output_path, report}.
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


def required(row, description, *names):
    value = get(row, *names)
    if value is None:
        fail(f"missing {description}; accepted fields: {', '.join(names)}")
    return value


def required_present(row, description, *names):
    for name in names:
        if name in row:
            return row[name]
    fail(f"missing {description} field; accepted fields: {', '.join(names)}")


def parse_time(value, description):
    if not isinstance(value, str) or not value:
        fail(f"{description} must be a nonempty ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as exc:
        fail(f"invalid {description}: {exc}")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        fail(f"{description} must include a timezone")
    return parsed.astimezone(timezone.utc)


def stable_id(row, kind):
    value = get(row, "id", "node_id", "nodeId", "number")
    if value is None or isinstance(value, (bool, dict, list)):
        fail(f"{kind} lacks stable id, node_id, nodeId, or number")
    return str(value)


def load_collection(config, direct_key, path_key):
    direct, path = direct_key in config, path_key in config
    if direct == path:
        fail(f"supply exactly one of {direct_key} and {path_key}")
    if direct:
        rows = config[direct_key]
    else:
        filename = config[path_key]
        if not isinstance(filename, str) or not filename:
            fail(f"{path_key} must be a nonempty string")
        try:
            with open(filename, encoding="utf-8") as handle:
                rows = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            fail(f"cannot load {path_key}: {exc}")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        fail(f"{direct_key} must be an array of objects")
    return rows


def deduplicate(rows, kind):
    found, result = set(), []
    for row in rows:
        key = stable_id(row, kind)
        if key not in found:
            found.add(key)
            result.append(row)
    return result


def label_names(row):
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
        fail("labels must be an array or GraphQL labels connection")
    result = []
    for label in value:
        if isinstance(label, str):
            result.append(label)
        elif isinstance(label, dict) and isinstance(label.get("name"), str):
            result.append(label["name"])
        else:
            fail("each label must be a string or an object with string name")
    return result


def author_login(row):
    value = get(row, "author", "user")
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    if isinstance(value, dict):
        value = value.get("login")
        if value is None:
            return None
        if not isinstance(value, str):
            fail("author login must be a string")
        return value or None
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
        fail("pr has invalid keys")
    if not isinstance(issue, dict) or set(issue) != {"total", "bug", "resolved_bugs"}:
        fail("issue has invalid keys")
    for group, keys in ((pr, ("total", "merged", "closed")), (issue, ("total", "bug", "resolved_bugs"))):
        for key in keys:
            if isinstance(group[key], bool) or not isinstance(group[key], int) or group[key] < 0:
                fail(f"{key} must be a nonnegative integer")
    if pr["merged"] > pr["total"] or pr["closed"] > pr["total"]:
        fail("PR outcome count exceeds total")
    if issue["bug"] > issue["total"] or issue["resolved_bugs"] > issue["bug"]:
        fail("issue outcome count exceeds cohort")
    average = pr["avg_merge_days"]
    if isinstance(average, bool) or not isinstance(average, float) or not math.isfinite(average) or average < 0 or round(average, 1) != average:
        fail("avg_merge_days must be a finite nonnegative float rounded to one decimal")
    if not isinstance(pr["top_contributor"], str) or not pr["top_contributor"].strip():
        fail("top_contributor must be a nonempty string")


def build(config):
    if not isinstance(config, dict):
        fail("stdin must be a JSON object")
    start = parse_time(required(config, "start", "start"), "start")
    end = parse_time(required(config, "end", "end"), "end")
    if end <= start:
        fail("end must be later than start")
    prs = deduplicate(load_collection(config, "pull_requests", "pull_requests_path"), "pull request")
    raw_issues = deduplicate(load_collection(config, "issues", "issues_path"), "issue")
    issues = [row for row in raw_issues if "pull_request" not in row and "pullRequest" not in row]

    total_pr = merged_count = closed_count = 0
    durations_us, authors = [], Counter()
    for row in prs:
        ident = stable_id(row, "pull request")
        created = parse_time(required(row, "PR creation time", "createdAt", "created_at"), f"PR {ident} createdAt")
        if not start <= created < end:
            continue
        state = required(row, "PR state", "state")
        if not isinstance(state, str):
            fail(f"PR {ident} state must be a string")
        raw_merged = required_present(row, "PR merge timestamp", "mergedAt", "merged_at")
        merged_at = None if raw_merged is None else parse_time(raw_merged, f"PR {ident} mergedAt")
        merged = merged_at is not None or state.upper() == "MERGED"
        if merged and merged_at is None:
            fail(f"merged PR {ident} lacks a merge timestamp")
        if merged:
            delta = merged_at - created
            elapsed = delta.days * 86400000000 + delta.seconds * 1000000 + delta.microseconds
            if elapsed < 0:
                fail(f"PR {ident} was merged before creation")
            durations_us.append(elapsed)
            merged_count += 1
        if state.upper() == "CLOSED" and not merged:
            closed_count += 1
        login = author_login(row)
        if login:
            authors[login] += 1
        total_pr += 1

    total_issue = bug_count = resolved_count = 0
    for row in issues:
        ident = stable_id(row, "issue")
        created = parse_time(required(row, "issue creation time", "createdAt", "created_at"), f"issue {ident} createdAt")
        if not start <= created < end:
            continue
        bug = any("bug" in name.casefold() for name in label_names(row))
        raw_closed = required_present(row, "issue closure timestamp", "closedAt", "closed_at")
        closed_at = None if raw_closed is None else parse_time(raw_closed, f"issue {ident} closedAt")
        total_issue += 1
        bug_count += int(bug)
        resolved_count += int(bug and closed_at is not None and start <= closed_at < end)

    if not authors:
        fail("no attributable PR author in cohort; cannot determine top_contributor")
    average = 0.0
    if durations_us:
        mean_days = Decimal(sum(durations_us)) / Decimal(len(durations_us)) / Decimal(86400000000)
        average = float(mean_days.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    top = min(authors, key=lambda login: (-authors[login], login.casefold(), login))
    report = {"pr": {"total": total_pr, "merged": merged_count, "closed": closed_count, "avg_merge_days": average, "top_contributor": top}, "issue": {"total": total_issue, "bug": bug_count, "resolved_bugs": resolved_count}}
    validate(report)
    return report


def main():
    try:
        config = json.load(sys.stdin)
        report = build(config)
        output_path = required(config, "output_path", "output_path")
        write_json(output_path, report)
        print(json.dumps({"output_path": output_path, "report": report}, ensure_ascii=False, allow_nan=False))
    except (InputError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(2)


if __name__ == "__main__":
    main()
