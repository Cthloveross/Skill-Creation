#!/usr/bin/env python3
"""Fetch GitHub PR/issue activity for a repo+window and write a report.json.

Reads an optional JSON config object from stdin, writes the report file, and
prints {"report":..., "audit":..., "written":...} as JSON to stdout.
See SKILL.md for the full schema and definitions.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

GRAPHQL_URL = "https://api.github.com/graphql"

DEFAULTS = {
    "repo": "cli/cli",
    "start": "2024-12-01T00:00:00Z",
    "end": "2025-01-01T00:00:00Z",
    "search_start": "2024-12-01",
    "search_end": "2024-12-31",
    "output": "/app/report.json",
    "closed_includes_merged": False,
    "tie_rule": "alpha",
}


def get_token():
    for k in ("GITHUB_TOKEN", "GH_TOKEN"):
        v = os.environ.get(k)
        if v:
            return v.strip()
    try:
        out = subprocess.run(["gh", "auth", "token"], capture_output=True,
                             text=True, timeout=20)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return None


def graphql(query, variables, token):
    body = json.dumps({"query": query, "variables": variables}).encode()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/vnd.github+json",
        "User-Agent": "skill-github-repo-activity",
        "Authorization": "bearer " + token,
    }
    last_err = None
    for attempt in range(5):
        req = urllib.request.Request(GRAPHQL_URL, data=body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
            if "errors" in data and data["errors"]:
                # retry on rate limit / transient; else raise
                msg = json.dumps(data["errors"])
                if "RATE_LIMITED" in msg or "timeout" in msg.lower():
                    last_err = RuntimeError(msg)
                    time.sleep(2 ** attempt * 2)
                    continue
                raise RuntimeError("GraphQL errors: " + msg)
            return data["data"]
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            if e.code in (403, 429, 502, 503):
                last_err = RuntimeError("HTTP %s: %s" % (e.code, detail))
                time.sleep(2 ** attempt * 2)
                continue
            raise RuntimeError("HTTP %s: %s" % (e.code, detail))
        except urllib.error.URLError as e:
            last_err = e
            time.sleep(2 ** attempt * 2)
    raise RuntimeError("GraphQL request failed after retries: %s" % last_err)


PR_QUERY = """
query($q:String!, $after:String){
  search(query:$q, type:ISSUE, first:100, after:$after){
    issueCount
    pageInfo{hasNextPage endCursor}
    nodes{
      __typename
      ... on PullRequest{
        number createdAt mergedAt closedAt state
        author{login}
      }
    }
  }
}
"""

ISSUE_QUERY = """
query($q:String!, $after:String){
  search(query:$q, type:ISSUE, first:100, after:$after){
    issueCount
    pageInfo{hasNextPage endCursor}
    nodes{
      __typename
      ... on Issue{
        number createdAt closedAt state
        labels(first:50){nodes{name}}
      }
    }
  }
}
"""


def paginate(query, q, token):
    nodes = []
    after = None
    pages = 0
    truncated = False
    while True:
        data = graphql(query, {"q": q, "after": after}, token)
        search = data["search"]
        nodes.extend(n for n in search["nodes"] if n)
        pages += 1
        pi = search["pageInfo"]
        if not pi["hasNextPage"]:
            break
        after = pi["endCursor"]
        if pages >= 10:  # GitHub search caps at 1000 results
            truncated = True
            break
    return nodes, truncated


def parse_dt(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def in_window(dt, start, end):
    return dt is not None and start <= dt < end


def compute(cfg):
    token = get_token()
    if not token:
        raise SystemExit(
            "ERROR: no GitHub token found. Set GITHUB_TOKEN/GH_TOKEN or run "
            "`gh auth login`; the GraphQL API requires authentication.")

    repo = cfg["repo"]
    start = parse_dt(cfg["start"])
    end = parse_dt(cfg["end"])
    s_start, s_end = cfg["search_start"], cfg["search_end"]

    pr_q = "repo:%s is:pr created:%s..%s" % (repo, s_start, s_end)
    iss_q = "repo:%s is:issue created:%s..%s" % (repo, s_start, s_end)

    pr_nodes, pr_trunc = paginate(PR_QUERY, pr_q, token)
    iss_nodes, iss_trunc = paginate(ISSUE_QUERY, iss_q, token)

    # dedupe by number
    prs = {n["number"]: n for n in pr_nodes if n.get("__typename") == "PullRequest"}
    issues = {n["number"]: n for n in iss_nodes if n.get("__typename") == "Issue"}

    # ---- PRs ----
    pr_total = 0
    pr_merged = 0
    pr_closed_unmerged = 0
    merge_days = []
    author_counts = {}
    for pr in prs.values():
        created = parse_dt(pr["createdAt"])
        if not in_window(created, start, end):
            continue
        pr_total += 1
        merged = parse_dt(pr["mergedAt"])
        closed = parse_dt(pr["closedAt"])
        if merged is not None:
            pr_merged += 1
            merge_days.append((merged - created).total_seconds() / 86400.0)
        elif closed is not None:
            pr_closed_unmerged += 1
        author = (pr.get("author") or {}).get("login")
        if author:
            author_counts[author] = author_counts.get(author, 0) + 1

    if cfg["closed_includes_merged"]:
        pr_closed = pr_merged + pr_closed_unmerged
    else:
        pr_closed = pr_closed_unmerged

    avg_merge_days = round(sum(merge_days) / len(merge_days), 1) if merge_days else 0.0

    if author_counts:
        best = max(author_counts.values())
        tied = sorted(a for a, c in author_counts.items() if c == best)
        top_contributor = tied[0]  # alpha tie rule
    else:
        top_contributor = ""

    # ---- Issues ----
    iss_total = 0
    iss_bug = 0
    resolved_bugs = 0
    for iss in issues.values():
        created = parse_dt(iss["createdAt"])
        if not in_window(created, start, end):
            continue
        iss_total += 1
        labels = [l["name"] for l in (iss.get("labels") or {}).get("nodes", [])]
        is_bug = any("bug" in (name or "").lower() for name in labels)
        if is_bug:
            iss_bug += 1
            closed = parse_dt(iss["closedAt"])
            if in_window(closed, start, end):
                resolved_bugs += 1

    report = {
        "pr": {
            "total": pr_total,
            "merged": pr_merged,
            "closed": pr_closed,
            "avg_merge_days": avg_merge_days,
            "top_contributor": top_contributor,
        },
        "issue": {
            "total": iss_total,
            "bug": iss_bug,
            "resolved_bugs": resolved_bugs,
        },
    }
    audit = {
        "pr_fetched": len(prs),
        "pr_in_window": pr_total,
        "issues_fetched": len(issues),
        "issues_in_window": iss_total,
        "search_truncated": bool(pr_trunc or iss_trunc),
    }
    return report, audit


def main():
    raw = sys.stdin.read().strip()
    cfg = dict(DEFAULTS)
    if raw:
        try:
            user = json.loads(raw)
            if isinstance(user, dict):
                cfg.update(user)
        except json.JSONDecodeError:
            pass
    report, audit = compute(cfg)
    out_path = cfg["output"]
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    print(json.dumps({"report": report, "audit": audit, "written": out_path}))


if __name__ == "__main__":
    main()
