#!/usr/bin/env python3
"""Preview a Jira ticket creation; require --apply for the live request."""

from __future__ import annotations

import argparse

from jira_common import (
    JiraError,
    adf_from_text,
    fail_cleanly,
    jira_config,
    jira_request,
    print_json,
    require_project_key,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--description")
    parser.add_argument("--project", help="Project key; defaults to JIRA_PROJECT_KEY")
    parser.add_argument("--issue-type", default="Task")
    parser.add_argument("--priority")
    parser.add_argument("--labels", nargs="*")
    parser.add_argument("--assignee-account-id")
    parser.add_argument("--parent", help="Parent issue key for a subtask")
    execution = parser.add_mutually_exclusive_group()
    execution.add_argument("--apply", action="store_true", help="Create the ticket; default is preview only")
    execution.add_argument("--dry-run", action="store_true", help="Explicitly request preview mode")
    args = parser.parse_args()

    config = jira_config()
    fields = {
        "project": {"key": require_project_key(config, args.project)},
        "summary": args.summary,
        "issuetype": {"name": args.issue_type},
    }
    if args.description is not None:
        fields["description"] = adf_from_text(args.description)
    if args.priority:
        fields["priority"] = {"name": args.priority}
    if args.labels is not None:
        fields["labels"] = args.labels
    if args.assignee_account_id:
        fields["assignee"] = {"accountId": args.assignee_account_id}
    if args.parent:
        fields["parent"] = {"key": args.parent.upper()}

    plan = {"method": "POST", "path": "/rest/api/3/issue", "payload": {"fields": fields}}
    if args.dry_run or not args.apply:
        print_json({"dryRun": True, **plan})
        return

    result = jira_request("POST", plan["path"], payload=plan["payload"], retry_safe_reads=False)
    print_json(
        {
            "created": True,
            "id": result.get("id"),
            "key": result.get("key"),
            "url": f'{config["site_url"]}/browse/{result.get("key")}',
        }
    )


if __name__ == "__main__":
    try:
        main()
    except (JiraError, ValueError) as error:
        fail_cleanly(error)
