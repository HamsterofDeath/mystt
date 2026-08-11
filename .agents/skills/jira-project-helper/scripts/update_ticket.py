#!/usr/bin/env python3
"""Preview Jira updates; require --apply for live changes."""

from __future__ import annotations

import argparse
import urllib.parse

from jira_common import (
    JiraError,
    adf_from_text,
    fail_cleanly,
    issue_record,
    jira_request,
    print_json,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("key", help="Issue key, for example BLG-1")
    parser.add_argument("--summary")
    parser.add_argument("--description")
    parser.add_argument("--priority")
    parser.add_argument("--labels", nargs="*")
    assignee = parser.add_mutually_exclusive_group()
    assignee.add_argument("--assignee-account-id")
    assignee.add_argument("--clear-assignee", action="store_true")
    parser.add_argument("--comment")
    parser.add_argument("--transition", help="Workflow transition name, case-insensitive")
    execution = parser.add_mutually_exclusive_group()
    execution.add_argument("--apply", action="store_true", help="Apply changes; default is preview only")
    execution.add_argument("--dry-run", action="store_true", help="Explicitly request preview mode")
    args = parser.parse_args()

    key = args.key.upper()
    encoded_key = urllib.parse.quote(key)
    fields = {}
    if args.summary is not None:
        fields["summary"] = args.summary
    if args.description is not None:
        fields["description"] = adf_from_text(args.description)
    if args.priority:
        fields["priority"] = {"name": args.priority}
    if args.labels is not None:
        fields["labels"] = args.labels
    if args.assignee_account_id:
        fields["assignee"] = {"accountId": args.assignee_account_id}
    elif args.clear_assignee:
        fields["assignee"] = None

    operations = []
    if fields:
        operations.append(
            {"method": "PUT", "path": f"/rest/api/3/issue/{encoded_key}", "payload": {"fields": fields}}
        )
    if args.comment is not None:
        operations.append(
            {
                "method": "POST",
                "path": f"/rest/api/3/issue/{encoded_key}/comment",
                "payload": {"body": adf_from_text(args.comment)},
            }
        )
    if args.transition:
        operations.append(
            {
                "method": "POST",
                "path": f"/rest/api/3/issue/{encoded_key}/transitions",
                "transitionName": args.transition,
            }
        )

    if not operations:
        parser.error("Provide at least one field, comment, assignment, or transition change")

    if args.dry_run or not args.apply:
        print_json({"dryRun": True, "issue": key, "operations": operations})
        return

    results = []
    for operation in operations:
        payload = operation.get("payload")
        if "transitionName" in operation:
            available = jira_request("GET", f"/rest/api/3/issue/{encoded_key}/transitions")
            wanted = operation["transitionName"].casefold()
            match = next(
                (transition for transition in available.get("transitions", []) if transition.get("name", "").casefold() == wanted),
                None,
            )
            if match is None:
                names = ", ".join(transition.get("name", "") for transition in available.get("transitions", []))
                raise JiraError(f"Transition '{operation['transitionName']}' is unavailable. Available: {names}")
            payload = {"transition": {"id": match["id"]}}
        jira_request(
            operation["method"],
            operation["path"],
            payload=payload,
            retry_safe_reads=False,
        )
        results.append({"method": operation["method"], "path": operation["path"], "ok": True})

    updated = jira_request(
        "GET",
        f"/rest/api/3/issue/{encoded_key}",
        query={"fields": "summary,status,assignee,priority,updated"},
    )
    print_json({"updated": True, "operations": results, "issue": issue_record(updated)})


if __name__ == "__main__":
    try:
        main()
    except (JiraError, ValueError) as error:
        fail_cleanly(error)
