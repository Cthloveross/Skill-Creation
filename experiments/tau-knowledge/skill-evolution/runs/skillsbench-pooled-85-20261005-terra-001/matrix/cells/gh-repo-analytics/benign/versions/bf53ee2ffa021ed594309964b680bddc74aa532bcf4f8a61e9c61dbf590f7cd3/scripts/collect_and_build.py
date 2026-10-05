#!/usr/bin/env python3
"""Collect complete GitHub REST creation cohorts using gh, then build a report.

Input: JSON object with owner, repo, start, end, output_path, optional audit_path.
Output: JSON status object on stdout; failures emit JSON errors and exit nonzero.
"""
import json
import subprocess
import sys
from urllib.parse import quote

from build_report import InputError, build, fail, need, timestamp, write_json


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
    """Fetch descending creation pages, including the boundary page, then stop."""
    result, page_number = [], 1
    while True:
        separator = "&" if "?" in endpoint else "?"
        page = gh_get(f"{endpoint}{separator}per_page=100&page={page_number}")
        if not page:
            return result
        result.extend(page)
        older_seen = False
        for row in page:
            value = row.get("created_at", row.get("createdAt"))
            if timestamp(value, "GitHub record created_at") < start:
                older_seen = True
        if older_seen or len(page) < 100:
            return result
        page_number += 1


def main():
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            fail("stdin must be a JSON object")
        owner, repo = need(config, "owner", "owner"), need(config, "repo", "repo")
        if not isinstance(owner, str) or not owner or not isinstance(repo, str) or not repo:
            fail("owner and repo must be nonempty strings")
        start, end = timestamp(need(config, "start", "start"), "start"), timestamp(need(config, "end", "end"), "end")
        if end <= start:
            fail("end must be later than start")
        output = need(config, "output_path", "output_path")
        repository = quote(owner, safe="") + "/" + quote(repo, safe="")
        prs = fetch_through_start(f"repos/{repository}/pulls?state=all&sort=created&direction=desc", start)
        issues = fetch_through_start(f"repos/{repository}/issues?state=all&sort=created&direction=desc", start)
        report, audit = build({"start": config["start"], "end": config["end"], "pull_requests": prs, "issues": issues})
        write_json(output, report)
        if config.get("audit_path") is not None:
            write_json(config["audit_path"], audit)
        print(json.dumps({"output_path": output, "report": report}, ensure_ascii=False, allow_nan=False))
    except (InputError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(2)


if __name__ == "__main__":
    main()
