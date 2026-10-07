#!/usr/bin/env python3
"""Collect complete GitHub REST creation cohorts with gh, then build a report.

Input stdin: owner, repo, start, end, output_path. Output stdout is a JSON
status object. This collector intentionally fails on retrieval errors; use
produce_report.py when a mandatory artifact must exist even on an outage.
"""
import json
import subprocess
import sys
from urllib.parse import quote

from build_report import InputError, build, fail, parse_time, required, write_json


def gh_get(endpoint):
    command = ["gh", "api", "--method", "GET", "-H", "Accept: application/vnd.github+json", endpoint]
    try:
        result = subprocess.run(command, text=True, capture_output=True, check=False)
    except OSError as exc:
        fail(f"cannot invoke gh CLI: {exc}")
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit status {result.returncode}"
        fail(f"GitHub retrieval failed for {endpoint}: {detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        fail(f"GitHub returned invalid JSON for {endpoint}: {exc}")
    if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
        fail(f"GitHub response for {endpoint} must be an array of objects")
    return payload


def fetch_through_start(endpoint, start):
    rows, page_number = [], 1
    while True:
        separator = "&" if "?" in endpoint else "?"
        page = gh_get(f"{endpoint}{separator}per_page=100&page={page_number}")
        if not page:
            return rows
        rows.extend(page)
        older_seen = any(parse_time(row.get("created_at", row.get("createdAt")), "GitHub record created_at") < start for row in page)
        if older_seen or len(page) < 100:
            return rows
        page_number += 1


def collect(config):
    if not isinstance(config, dict):
        fail("stdin must be a JSON object")
    owner, repo = required(config, "owner", "owner"), required(config, "repo", "repo")
    if not isinstance(owner, str) or not owner or not isinstance(repo, str) or not repo:
        fail("owner and repo must be nonempty strings")
    start = parse_time(required(config, "start", "start"), "start")
    end = parse_time(required(config, "end", "end"), "end")
    if end <= start:
        fail("end must be later than start")
    repository = quote(owner, safe="") + "/" + quote(repo, safe="")
    prs = fetch_through_start(f"repos/{repository}/pulls?state=all&sort=created&direction=desc", start)
    issues = fetch_through_start(f"repos/{repository}/issues?state=all&sort=created&direction=desc", start)
    return {"start": config["start"], "end": config["end"], "pull_requests": prs, "issues": issues}


def main():
    try:
        config = json.load(sys.stdin)
        source = collect(config)
        report = build(source)
        output_path = required(config, "output_path", "output_path")
        write_json(output_path, report)
        print(json.dumps({"output_path": output_path, "report": report}, ensure_ascii=False, allow_nan=False))
    except (InputError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(2)


if __name__ == "__main__":
    main()
