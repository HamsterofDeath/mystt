#!/usr/bin/env python3
"""Read-only health check: config resolution, token validity, reachable endpoints."""

from __future__ import annotations

from jira_common import JiraError, config_source, fail_cleanly, jira_request, print_json

VARIABLES = ["JIRA_API_TOKEN", "JIRA_EMAIL", "JIRA_API_BASE_URL", "JIRA_SITE_URL", "JIRA_PROJECT_KEY"]


def main() -> None:
    config_report = {}
    missing = []
    for name in VARIABLES:
        value, origin = config_source(name)
        if value is None:
            missing.append(name)
            config_report[name] = {"set": False}
        elif name == "JIRA_API_TOKEN":
            config_report[name] = {"set": True, "origin": origin, "length": len(value), "prefix": value[:5]}
        else:
            config_report[name] = {"set": True, "origin": origin, "value": value}

    required_missing = [name for name in missing if name != "JIRA_PROJECT_KEY"]
    if required_missing:
        print_json({"ok": False, "config": config_report, "error": f"missing: {', '.join(required_missing)}"})
        raise SystemExit(1)

    checks: dict[str, object] = {}

    try:
        myself = jira_request("GET", "/rest/api/3/myself")
        checks["myself"] = {
            "ok": True,
            "displayName": myself.get("displayName"),
            "emailAddress": myself.get("emailAddress"),
            "accountId": myself.get("accountId"),
        }
    except JiraError as error:
        checks["myself"] = {"ok": False, "error": str(error)}
        print_json({"ok": False, "config": config_report, "checks": checks})
        raise SystemExit(1)

    try:
        projects = jira_request("GET", "/rest/api/3/project") or []
        checks["projects"] = {
            "ok": True,
            "count": len(projects),
            "keys": [project.get("key") for project in projects],
        }
    except JiraError as error:
        checks["projects"] = {"ok": False, "error": str(error)}

    try:
        result = jira_request(
            "POST",
            "/rest/api/3/search/jql",
            payload={"jql": "created >= -30d ORDER BY updated DESC", "maxResults": 1, "fields": ["summary"]},
            retry_safe_reads=False,
        )
        checks["search"] = {"ok": True, "sampleCount": len((result or {}).get("issues", []))}
    except JiraError as error:
        checks["search"] = {"ok": False, "error": str(error)}

    ok = all(check.get("ok") for check in checks.values())
    print_json({"ok": ok, "config": config_report, "checks": checks})
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except (JiraError, ValueError) as error:
        fail_cleanly(error)
