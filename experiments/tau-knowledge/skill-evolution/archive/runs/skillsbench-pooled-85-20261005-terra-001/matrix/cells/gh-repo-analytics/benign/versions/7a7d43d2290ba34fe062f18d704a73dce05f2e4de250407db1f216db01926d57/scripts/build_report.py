#!/usr/bin/env python3
"""Build a validated GitHub monthly report from supplied JSON record arrays."""

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


def field(record, *names, default=None):
    for name in names:
        if name in record:
            return record[name]
    return default


def required_field(record, description, *names):
    value = field(record, *names, default=None)
    if value is None:
        fail(f"record missing {description} (accepted fields: {', '.join(names)})")
    return value


def nullable_present_field(record, description, *names):
    for name in names:
        if name in record:
            return record[name]
    fail(f"record missing {description} field (accepted fields: {', '.join(names)})")


def parse_time(value, description):
    if not isinstance(value, str) or not value:
        fail(f"{description} must be a nonempty timezone-aware ISO-8601 string")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        fail(f"{description} is not ISO-8601: {exc}")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        fail(f"{description} must include a timezone")
    return parsed.astimezone(timezone.utc)


def identifier(record, kind):
    value = field(record, "id", "node_id", "nodeId", "number", default=None)
    if value is None or isinstance(value, (dict, list, bool)):
        fail(f"{kind} record lacks a stable id, node_id, nodeId, or number")
    return str(value)


def load_collection(config, direct_key, path_key):
    direct = direct_key in config
    from_path = path_key in config
    if direct == from_path:
        fail(f"supply exactly one of {direct_key} and {path_key}")
    if direct:
        records = config[direct_key]
    else:
        path = config[path_key]
        if not isinstance(path, str) or not path:
            fail(f"{path_key} must be a nonempty path string")
        try:
            with open(path, encoding="utf-8") as source:
                records = json.load(source)
        except (OSError, json.JSONDecodeError) as exc:
            fail(f"cannot read {path_key}: {exc}")
    if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
        fail(f"{direct_key} source must be a JSON array of objects")
    return records


def deduplicate(records, kind):
    output, seen = [], set()
    for record in records:
        key = identifier(record, kind)
        if key not in seen:
            seen.add(key)
            output.append(record)
    return output


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
            labels = [x.get("node") for x in labels["edges"] if isinstance(x, dict)]
        else:
            fail("labels object must contain nodes or edges array")
    if not isinstance(labels, list):
        fail("labels must be an array, nodes object, or edges object")
    result = []
    for item in labels:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict) and isinstance(item.get("name"), str):
            result.append(item["name"])
        else:
            fail("each label must be a string or object with string name")
    return result


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


def is_rest_issue_pr(record):
    return "pull_request" in record or "pullRequest" in record


def atomic_json_write(path_text, value):
    if not isinstance(path_text, str) or not path_text:
        fail("output path must be a nonempty string")
    destination = Path(path_text)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(prefix=".report-", suffix=".tmp", dir=str(destination.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(value, out, indent=2, ensure_ascii=False, allow_nan=False)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp_path, destination)
    except OSError as exc:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
        fail(f"cannot write {destination}: {exc}")


def validate_report(report):
    if not isinstance(report, dict) or set(report) != {"pr", "issue"}:
        fail("report must contain exactly pr and issue")
    pr, issue = report["pr"], report["issue"]
    if not isinstance(pr, dict) or set(pr) != {"total", "merged", "closed", "avg_merge_days", "top_contributor"}:
        fail("report.pr keys are invalid")
    if not isinstance(issue, dict) or set(issue) != {"total", "bug", "resolved_bugs"}:
        fail("report.issue keys are invalid")
    for section, keys in ((pr, ("total", "merged", "closed")), (issue, ("total", "bug", "resolved_bugs"))):
        for key in keys:
            if isinstance(section[key], bool) or not isinstance(section[key], int) or section[key] < 0:
                fail(f"report count {key} must be a nonnegative integer")
    if pr["merged"] > pr["total"] or pr["closed"] > pr["total"]:
        fail("PR outcome counts exceed cohort total")
    if issue["bug"] > issue["total"] or issue["resolved_bugs"] > issue["bug"]:
        fail("issue outcome counts exceed cohort total")
    avg = pr["avg_merge_days"]
    if isinstance(avg, bool) or not isinstance(avg, float) or not math.isfinite(avg) or avg < 0 or round(avg, 1) != avg:
        fail("report.pr.avg_merge_days must be finite nonnegative float rounded to one decimal")
    if not isinstance(pr["top_contributor"], str) or not pr["top_contributor"].strip():
        fail("report.pr.top_contributor must be a nonempty string")


def build_report(config):
    if not isinstance(config, dict):
        fail("stdin must contain a JSON object")
    start = parse_time(required_field(config, "start", "start"), "start")
    end = parse_time(required_field(config, "end", "end"), "end")
    if end <= start:
        fail("end must be later than start")

    prs = deduplicate(load_collection(config, "pull_requests", "pull_requests_path"), "pull request")
    issues = [x for x in deduplicate(load_collection(config, "issues", "issues_path"), "issue") if not is_rest_issue_pr(x)]
    durations, authors, pr_audit = [], Counter(), []
    merged_count = closed_count = total_pr = 0

    for row in prs:
        rid = identifier(row, "pull request")
        created = parse_time(required_field(row, "PR creation timestamp", "createdAt", "created_at"), f"PR {rid} createdAt")
        if not in_window(created, start, end):
            continue
        state = required_field(row, "PR current state", "state")
        if not isinstance(state, str):
            fail(f"PR {rid} state must be a string")
        raw_merged = nullable_present_field(row, "PR merge timestamp", "mergedAt", "merged_at")
        merged_time = None if raw_merged is None else parse_time(raw_merged, f"PR {rid} mergedAt")
        merged = merged_time is not None or state.upper() == "MERGED"
        if merged and merged_time is None:
            fail(f"merged PR {rid} lacks mergedAt needed for duration")
        closed = state.upper() == "CLOSED" and not merged
        if merged:
            micros = int((merged_time - created).total_seconds() * 1000000)
            if micros < 0:
                fail(f"PR {rid} merge time precedes creation")
            durations.append(micros)
            merged_count += 1
        if closed:
            closed_count += 1
        login = author_login(row)
        if login:
            authors[login] += 1
        total_pr += 1
        pr_audit.append({"id": rid, "created_at": created.isoformat(), "state": state, "merged_at": None if merged_time is None else merged_time.isoformat(), "merged": merged, "closed_unmerged": closed, "author": login})

    bug_count = resolved_count = total_issue = 0
    issue_audit = []
    for row in issues:
        rid = identifier(row, "issue")
        created = parse_time(required_field(row, "issue creation timestamp", "createdAt", "created_at"), f"issue {rid} createdAt")
        if not in_window(created, start, end):
            continue
        labels = label_names(row)
        bug = any("bug" in name.casefold() for name in labels)
        raw_closed = nullable_present_field(row, "issue closure timestamp", "closedAt", "closed_at")
        closed_at = None if raw_closed is None else parse_time(raw_closed, f"issue {rid} closedAt")
        resolved = bug and closed_at is not None and in_window(closed_at, start, end)
        total_issue += 1
        bug_count += int(bug)
        resolved_count += int(resolved)
        issue_audit.append({"id": rid, "created_at": created.isoformat(), "labels": labels, "bug": bug, "closed_at": None if closed_at is None else closed_at.isoformat(), "resolved_bug_in_window": resolved})

    if not authors:
        fail("no attributable cohort PR author; cannot produce required nonempty top_contributor")
    average = 0.0
    if durations:
        mean = Decimal(sum(durations)) / Decimal(len(durations)) / Decimal(86400000000)
        average = float(mean.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    top = min(authors, key=lambda name: (-authors[name], name.casefold(), name))
    report = {"pr": {"total": total_pr, "merged": merged_count, "closed": closed_count, "avg_merge_days": average, "top_contributor": top}, "issue": {"total": total_issue, "bug": bug_count, "resolved_bugs": resolved_count}}
    validate_report(report)
    return report, {"pull_requests": pr_audit, "issues": issue_audit}


def main():
    try:
        config = json.load(sys.stdin)
        report, audit = build_report(config)
        output = required_field(config, "output_path", "output_path")
        atomic_json_write(output, report)
        if config.get("audit_path") is not None:
            atomic_json_write(config["audit_path"], audit)
        print(json.dumps({"output_path": output, "report": report}, ensure_ascii=False, allow_nan=False))
    except (InputError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(2)


if __name__ == "__main__":
    main()
