#!/usr/bin/env python3
"""Find Jira tickets by exact key, text, or explicit JQL."""

from __future__ import annotations

import argparse
import re
import urllib.parse

from jira_common import (
    JiraError,
    fail_cleanly,
    issue_record,
    jira_config,
    jira_request,
    print_json,
    require_project_key,
)


FIELDS = ["summary", "status", "assignee", "priority", "updated"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Issue key, search text, or JQL with --jql")
    parser.add_argument("--project", help="Project key; defaults to JIRA_PROJECT_KEY")
    parser.add_argument("--limit", type=int, default=20, help="Maximum results (1-100)")
    parser.add_argument("--jql", action="store_true", help="Treat query as complete JQL")
    args = parser.parse_args()

    if not 1 <= args.limit <= 100:
        parser.error("--limit must be between 1 and 100")

    if not args.jql and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*-\d+", args.query):
        key = args.query.upper()
        issue = jira_request(
            "GET",
            f"/rest/api/3/issue/{urllib.parse.quote(key)}",
            query={"fields": ",".join(FIELDS)},
        )
        print_json(issue_record(issue))
        return

    if args.jql:
        jql = args.query
    else:
        project = require_project_key(jira_config(), args.project)
        term = args.query.replace("\\", "\\\\").replace('"', '\\"')
        jql = f'project = "{project}" AND text ~ "{term}" ORDER BY updated DESC'

    response = jira_request(
        "POST",
        "/rest/api/3/search/jql",
        payload={"jql": jql, "maxResults": args.limit, "fields": FIELDS},
    )
    issues = [issue_record(issue) for issue in response.get("issues", [])]
    print_json({"jql": jql, "count": len(issues), "issues": issues})


if __name__ == "__main__":
    try:
        main()
    except (JiraError, ValueError) as error:
        fail_cleanly(error)
