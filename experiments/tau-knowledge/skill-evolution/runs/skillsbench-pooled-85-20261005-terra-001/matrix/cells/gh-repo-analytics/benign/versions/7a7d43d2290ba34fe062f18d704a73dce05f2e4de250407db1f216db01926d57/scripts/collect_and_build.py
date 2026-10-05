#!/usr/bin/env python3
"""Collect paginated current GitHub REST records with gh and build a report."""

import json
import subprocess
import sys
from urllib.parse import quote

from build_report import InputError, build_report, fail, parse_time, required_field, atomic_json_write


def gh_page(endpoint):
    command = ["gh", "api", "--method", "GET", "-H", "Accept: application/vnd.github+json", endpoint]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        fail(f"cannot invoke gh CLI: {exc}")
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit status {completed.returncode}"
        fail(f"GitHub retrieval failed for {endpoint}: {detail}")
    try:
        page = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        fail(f"GitHub response for {endpoint} was not JSON: {exc}")
    if not isinstance(page, list) or not all(isinstance(row, dict) for row in page):
        fail(f"GitHub response for {endpoint} was not an array of objects")
    return page


def created_at(row, description):
    value = row.get("created_at", row.get("createdAt"))
    return parse_time(value, description)


def collect_created_desc(base_endpoint, start):
    """Fetch pages sorted descending by creation until an older record is seen."""
    all_rows = []
    page_number = 1
    while True:
        separator = "&" if "?" in base_endpoint else "?"
        page = gh_page(f"{base_endpoint}{separator}per_page=100&page={page_number}")
        if not page:
            break
        all_rows.extend(page)
        oldest_is_before_start = False
        for row in page:
            if created_at(row, "GitHub record created_at") < start:
                oldest_is_before_start = True
        if oldest_is_before_start:
            break
        if len(page) < 100:
            break
        page_number += 1
    return all_rows


def main():
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            fail("stdin must contain a JSON object")
        owner = required_field(config, "owner", "owner")
        repo = required_field(config, "repo", "repo")
        if not isinstance(owner, str) or not owner or not isinstance(repo, str) or not repo:
            fail("owner and repo must be nonempty strings")
        start = parse_time(required_field(config, "start", "start"), "start")
        end = parse_time(required_field(config, "end", "end"), "end")
        if end <= start:
            fail("end must be later than start")
        output = required_field(config, "output_path", "output_path")

        repo_path = quote(owner, safe="") + "/" + quote(repo, safe="")
        prs = collect_created_desc(f"repos/{repo_path}/pulls?state=all&sort=created&direction=desc", start)
        issues = collect_created_desc(f"repos/{repo_path}/issues?state=all&sort=created&direction=desc", start)
        report, audit = build_report({"start": config["start"], "end": config["end"], "pull_requests": prs, "issues": issues})
        atomic_json_write(output, report)
        if config.get("audit_path") is not None:
            atomic_json_write(config["audit_path"], audit)
        print(json.dumps({"output_path": output, "report": report}, ensure_ascii=False, allow_nan=False))
    except (InputError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(2)


if __name__ == "__main__":
    main()
