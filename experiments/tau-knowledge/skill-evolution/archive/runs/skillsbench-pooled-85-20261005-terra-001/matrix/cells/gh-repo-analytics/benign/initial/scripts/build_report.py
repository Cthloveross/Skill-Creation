#!/usr/bin/env python3
"""Aggregate supplied GitHub PR and issue records into a monthly report.

Input and output are JSON on stdin/stdout.  See SKILL.md for the public schema.
"""

import json
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


def field(record, *names, default=None):
    for name in names:
        if name in record:
            return record[name]
    return default


def required_field(record, description, *names):
    value = field(record, *names, default=None)
    if value is None:
        fail("record missing " + description + " (accepted fields: " + ", ".join(names) + ")")
    return value


def parse_time(value, description):
    if not isinstance(value, str) or not value:
        fail(description + " must be a nonempty timezone-aware ISO-8601 string")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        fail(description + " is not ISO-8601: " + str(exc))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        fail(description + " must include a timezone")
    return parsed.astimezone(timezone.utc)


def identifier(record, kind):
    value = field(record, "id", "node_id", "nodeId", "number", default=None)
    if value is None or isinstance(value, (dict, list)):
        fail(kind + " record lacks a stable id, node_id, nodeId, or number")
    return str(value)


def load_collection(config, direct_key, path_key):
    has_direct = direct_key in config
    has_path = path_key in config
    if has_direct == has_path:
        fail("supply exactly one of " + direct_key + " and " + path_key)
    if has_direct:
        records = config[direct_key]
    else:
        path = config[path_key]
        if not isinstance(path, str) or not path:
            fail(path_key + " must be a nonempty path string")
        try:
            with open(path, "r", encoding="utf-8") as source:
                records = json.load(source)
        except (OSError, json.JSONDecodeError) as exc:
            fail("cannot read " + path_key + ": " + str(exc))
    if not isinstance(records, list):
        fail(direct_key + " source must be a JSON array")
    if not all(isinstance(item, dict) for item in records):
        fail(direct_key + " records must all be JSON objects")
    return records


def deduplicate(records, kind):
    seen = set()
    unique = []
    for record in records:
        key = identifier(record, kind)
        if key not in seen:
            seen.add(key)
            unique.append(record)
    return unique


def in_window(instant, start, end):
    return start <= instant < end


def label_names(record):
    labels = field(record, "labels", default=[])
    if labels is None:
        return []
    if isinstance(labels, dict):
        if isinstance(labels.get("nodes"), list):
            labels = labels["nodes"]
        elif isinstance(labels.get("edges"), list):
            labels = [edge.get("node") for edge in labels["edges"] if isinstance(edge, dict)]
        else:
            fail("labels object must contain a nodes or edges array")
    if not isinstance(labels, list):
        fail("labels must be an array, nodes object, or edges object")
    names = []
    for label in labels:
        if isinstance(label, str):
            names.append(label)
        elif isinstance(label, dict) and isinstance(label.get("name"), str):
            names.append(label["name"])
        else:
            fail("each label must be a string or object with string name")
    return names


def author_login(record):
    author = field(record, "author", "user", default=None)
    if author is None:
        return None
    if isinstance(author, str):
        return author or None
    if isinstance(author, dict):
        login = author.get("login")
        if login is None:
            return None
        if not isinstance(login, str):
            fail("author login must be a string or null")
        return login or None
    fail("author/user must be an object, string, or null")


def is_rest_issue_pull_request(record):
    # REST /issues identifies PR-shaped entries with this key, even when its
    # value is an empty object. GraphQL Issue nodes do not carry it.
    return "pull_request" in record or "pullRequest" in record


def duration_microseconds(start, finish):
    delta = finish - start
    return ((delta.days * 86400 + delta.seconds) * 1000000) + delta.microseconds


def atomic_json_write(path_text, value):
    if not isinstance(path_text, str) or not path_text:
        fail("output path must be a nonempty string")
    destination = Path(path_text)
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    try:
        fd, temporary = tempfile.mkstemp(prefix=".report-", suffix=".tmp", dir=str(destination.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(encoded)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, destination)
    except OSError as exc:
        try:
            os.unlink(temporary)
        except (OSError, UnboundLocalError):
            pass
        fail("cannot write " + str(destination) + ": " + str(exc))


def validate_report(report):
    expected_top = {"pr", "issue"}
    expected_pr = {"total", "merged", "closed", "avg_merge_days", "top_contributor"}
    expected_issue = {"total", "bug", "resolved_bugs"}
    if not isinstance(report, dict) or set(report) != expected_top:
        fail("report top-level keys are invalid")
    if not isinstance(report["pr"], dict) or set(report["pr"]) != expected_pr:
        fail("report.pr keys are invalid")
    if not isinstance(report["issue"], dict) or set(report["issue"]) != expected_issue:
        fail("report.issue keys are invalid")
    for key in ("total", "merged", "closed"):
        value = report["pr"][key]
        if isinstance(value, bool) or not isinstance(value, int):
            fail("report.pr." + key + " must be an integer")
    for key in ("total", "bug", "resolved_bugs"):
        value = report["issue"][key]
        if isinstance(value, bool) or not isinstance(value, int):
            fail("report.issue." + key + " must be an integer")
    if isinstance(report["pr"]["avg_merge_days"], bool) or not isinstance(report["pr"]["avg_merge_days"], float):
        fail("report.pr.avg_merge_days must be a float")
    if not isinstance(report["pr"]["top_contributor"], str):
        fail("report.pr.top_contributor must be a string")


def build_report(config):
    if not isinstance(config, dict):
        fail("stdin must contain a JSON object")
    start = parse_time(required_field(config, "start", "start"), "start")
    end = parse_time(required_field(config, "end", "end"), "end")
    if end <= start:
        fail("end must be later than start")

    pull_requests = deduplicate(load_collection(config, "pull_requests", "pull_requests_path"), "pull request")
    raw_issues = deduplicate(load_collection(config, "issues", "issues_path"), "issue")
    issues = [record for record in raw_issues if not is_rest_issue_pull_request(record)]

    cohort_prs = []
    merge_durations = []
    contributors = Counter()
    pr_audit = []
    for record in pull_requests:
        record_id = identifier(record, "pull request")
        created = parse_time(required_field(record, "PR creation timestamp", "createdAt", "created_at"), "PR " + record_id + " createdAt")
        if not in_window(created, start, end):
            continue
        state = required_field(record, "PR current state", "state")
        if not isinstance(state, str):
            fail("PR " + record_id + " state must be a string")
        raw_merged = field(record, "mergedAt", "merged_at", default=None)
        merged_time = None if raw_merged is None else parse_time(raw_merged, "PR " + record_id + " mergedAt")
        merged = merged_time is not None or state.upper() == "MERGED"
        closed = state.upper() == "CLOSED" and not merged
        if merged_time is not None:
            micros = duration_microseconds(created, merged_time)
            if micros < 0:
                fail("PR " + record_id + " merge time precedes creation time")
            merge_durations.append(micros)
        login = author_login(record)
        if login is not None:
            contributors[login] += 1
        cohort_prs.append((merged, closed))
        pr_audit.append({"id": record_id, "created_at": created.isoformat(), "state": state,
                         "merged_at": None if merged_time is None else merged_time.isoformat(),
                         "merged": merged, "closed_unmerged": closed, "author": login})

    cohort_issues = []
    issue_audit = []
    for record in issues:
        record_id = identifier(record, "issue")
        created = parse_time(required_field(record, "issue creation timestamp", "createdAt", "created_at"), "issue " + record_id + " createdAt")
        if not in_window(created, start, end):
            continue
        labels = label_names(record)
        bug = any("bug" in name.casefold() for name in labels)
        raw_closed = required_field(record, "issue closure timestamp field", "closedAt", "closed_at")
        closed_time = None if raw_closed is None else parse_time(raw_closed, "issue " + record_id + " closedAt")
        resolved_bug = bug and closed_time is not None and in_window(closed_time, start, end)
        cohort_issues.append((bug, resolved_bug))
        issue_audit.append({"id": record_id, "created_at": created.isoformat(), "labels": labels,
                            "bug": bug, "closed_at": None if closed_time is None else closed_time.isoformat(),
                            "resolved_bug_in_window": resolved_bug})

    if merge_durations:
        mean_days = (Decimal(sum(merge_durations)) /
                     Decimal(len(merge_durations)) /
                     Decimal(86400000000))
        average = float(mean_days.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    else:
        average = 0.0

    if contributors:
        top = min(contributors, key=lambda login: (-contributors[login], login.casefold(), login))
    else:
        top = ""

    report = {
        "pr": {
            "total": len(cohort_prs),
            "merged": sum(merged for merged, _ in cohort_prs),
            "closed": sum(closed for _, closed in cohort_prs),
            "avg_merge_days": average,
            "top_contributor": top,
        },
        "issue": {
            "total": len(cohort_issues),
            "bug": sum(bug for bug, _ in cohort_issues),
            "resolved_bugs": sum(resolved for _, resolved in cohort_issues),
        },
    }
    validate_report(report)
    return report, {"pull_requests": pr_audit, "issues": issue_audit}


def main():
    try:
        config = json.load(sys.stdin)
        report, audit = build_report(config)
        output_path = required_field(config, "output_path", "output_path")
        atomic_json_write(output_path, report)
        audit_path = config.get("audit_path")
        if audit_path is not None:
            atomic_json_write(audit_path, audit)
        print(json.dumps({"report": report, "output_path": output_path}, ensure_ascii=False, allow_nan=False))
    except (InputError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(2)


if __name__ == "__main__":
    main()
