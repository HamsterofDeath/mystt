#!/usr/bin/env python3
"""List, validate, create, or update Jira Cloud projects safely."""

from __future__ import annotations

import argparse
import re
import urllib.parse

from jira_common import JiraError, fail_cleanly, jira_config, jira_request, print_json


DEFAULT_SOFTWARE_TEMPLATE = "com.pyxis.greenhopper.jira:gh-simplified-agility-kanban"


def project_record(project: dict) -> dict:
    config = jira_config()
    key = project.get("key")
    return {
        "id": project.get("id"),
        "key": key,
        "name": project.get("name"),
        "projectType": project.get("projectTypeKey"),
        "simplified": project.get("simplified"),
        "style": project.get("style"),
        "url": f'{config["site_url"]}/browse/{key}',
    }


def all_projects() -> list[dict]:
    try:
        return _paged_projects()
    except JiraError as error:
        # Scoped tokens without the project/search scope get 401/403 there;
        # the plain /project endpoint works with narrower scopes.
        if error.status not in (401, 403):
            raise
    return jira_request("GET", "/rest/api/3/project") or []


def _paged_projects() -> list[dict]:
    projects: list[dict] = []
    start_at = 0
    while True:
        page = jira_request(
            "GET",
            "/rest/api/3/project/search",
            query={"startAt": start_at, "maxResults": 50, "orderBy": "key"},
        )
        values = page.get("values") or []
        projects.extend(values)
        if page.get("isLast", start_at + len(values) >= page.get("total", 0)):
            break
        if not values:
            raise JiraError("Jira project pagination returned an empty non-final page")
        start_at += len(values)
    return projects


def parse_project(value: str) -> tuple[str, str]:
    key, separator, name = value.partition("=")
    key = key.strip().upper()
    name = name.strip()
    if not separator or not key or not name:
        raise argparse.ArgumentTypeError("Use KEY=Project Name")
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
        raise argparse.ArgumentTypeError(f"Invalid project key syntax: {key}")
    return key, name


def validation_errors(key: str) -> list[str]:
    result = jira_request("GET", "/rest/api/3/projectvalidate/key", query={"key": key})
    errors = [str(message) for message in result.get("errorMessages", [])]
    errors.extend(str(message) for message in (result.get("errors") or {}).values())
    return errors


def add_execution_flags(parser: argparse.ArgumentParser) -> None:
    execution = parser.add_mutually_exclusive_group()
    execution.add_argument("--apply", action="store_true", help="Apply changes; default is preview only")
    execution.add_argument("--dry-run", action="store_true", help="Explicitly request preview mode")


def command_list() -> None:
    projects = [project_record(project) for project in all_projects()]
    print_json({"count": len(projects), "projects": projects})


def command_validate(keys: list[str]) -> None:
    results = []
    for raw_key in keys:
        key = raw_key.strip().upper()
        errors = validation_errors(key)
        results.append({"key": key, "valid": not errors, "errors": errors})
    print_json({"count": len(results), "valid": all(result["valid"] for result in results), "results": results})


def command_create(args: argparse.Namespace) -> None:
    requested = args.project
    if len({key for key, _ in requested}) != len(requested):
        raise JiraError("The create request contains duplicate project keys")
    if len({name.casefold() for _, name in requested}) != len(requested):
        raise JiraError("The create request contains duplicate project names")

    existing = all_projects()
    existing_by_key = {str(project.get("key", "")).upper(): project for project in existing}
    existing_by_name = {str(project.get("name", "")).casefold(): project for project in existing}
    planned: list[dict] = []
    skipped: list[dict] = []
    conflicts: list[dict] = []

    for key, name in requested:
        key_match = existing_by_key.get(key)
        name_match = existing_by_name.get(name.casefold())
        if key_match:
            if str(key_match.get("name", "")).casefold() == name.casefold():
                skipped.append({"key": key, "name": name, "reason": "already exists"})
            else:
                conflicts.append(
                    {
                        "key": key,
                        "name": name,
                        "reason": f'key belongs to {key_match.get("name")}',
                    }
                )
            continue
        if name_match:
            conflicts.append(
                {
                    "key": key,
                    "name": name,
                    "reason": f'name already uses key {name_match.get("key")}',
                }
            )
            continue
        errors = validation_errors(key)
        if errors:
            conflicts.append({"key": key, "name": name, "reason": "; ".join(errors)})
            continue
        planned.append({"key": key, "name": name})

    if conflicts:
        print_json(
            {
                "dryRun": True,
                "requested": len(requested),
                "planned": planned,
                "skipped": skipped,
                "conflicts": conflicts,
            }
        )
        raise JiraError("Resolve all project conflicts before applying the batch")

    lead_account_id = args.lead_account_id
    lead_display_name = None
    if not lead_account_id:
        current_user = jira_request("GET", "/rest/api/3/myself")
        lead_account_id = current_user.get("accountId")
        lead_display_name = current_user.get("displayName")
    if not lead_account_id:
        raise JiraError("Could not resolve a Jira project lead account id")

    operations = []
    for project in planned:
        payload = {
            "key": project["key"],
            "name": project["name"],
            "projectTypeKey": args.project_type,
            "projectTemplateKey": args.template,
            "leadAccountId": lead_account_id,
            "assigneeType": args.assignee_type,
        }
        operations.append({"method": "POST", "path": "/rest/api/3/project", "payload": payload})

    preview = {
        "dryRun": not args.apply,
        "requested": len(requested),
        "createCount": len(operations),
        "skipCount": len(skipped),
        "lead": lead_display_name or "explicit account id",
        "operations": operations,
        "skipped": skipped,
    }
    if args.dry_run or not args.apply:
        print_json(preview)
        return

    created = []
    failures = []
    for operation in operations:
        payload = operation["payload"]
        try:
            result = jira_request(
                operation["method"],
                operation["path"],
                payload=payload,
                retry_safe_reads=False,
            )
            created.append({"id": result.get("id"), "key": result.get("key"), "name": payload["name"]})
        except JiraError as error:
            failures.append({"key": payload["key"], "name": payload["name"], "error": str(error)})

    verified = []
    for project in created:
        encoded_key = urllib.parse.quote(str(project["key"]))
        verified.append(project_record(jira_request("GET", f"/rest/api/3/project/{encoded_key}")))

    print_json(
        {
            "createdCount": len(created),
            "skippedCount": len(skipped),
            "failureCount": len(failures),
            "created": created,
            "skipped": skipped,
            "failures": failures,
            "verified": verified,
        }
    )
    if failures:
        raise JiraError("One or more Jira projects failed to create; rerun the same command safely")


def command_update(args: argparse.Namespace) -> None:
    key = args.key.upper()
    if not args.new_key and args.name is None:
        raise JiraError("Provide --new-key, --name, or both")
    encoded_key = urllib.parse.quote(key)
    current = jira_request("GET", f"/rest/api/3/project/{encoded_key}")
    payload = {}
    if args.new_key:
        new_key = args.new_key.upper()
        errors = validation_errors(new_key)
        if errors:
            raise JiraError("; ".join(errors))
        payload["key"] = new_key
    if args.name is not None:
        payload["name"] = args.name

    preview = {
        "dryRun": not args.apply,
        "current": {"id": current.get("id"), "key": current.get("key"), "name": current.get("name")},
        "operation": {
            "method": "PUT",
            "path": f'/rest/api/3/project/{current.get("id")}',
            "payload": payload,
        },
    }
    if args.dry_run or not args.apply:
        print_json(preview)
        return

    updated = jira_request(
        "PUT",
        preview["operation"]["path"],
        payload=payload,
        retry_safe_reads=False,
    )
    print_json({"updated": True, "project": project_record(updated)})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List every visible Jira project")

    validate = subparsers.add_parser("validate", help="Validate one or more unused project keys")
    validate.add_argument("--key", action="append", required=True)

    create = subparsers.add_parser("create", help="Preview or create one or more projects")
    create.add_argument("--project", action="append", type=parse_project, required=True, metavar="KEY=NAME")
    create.add_argument("--project-type", default="software")
    create.add_argument("--template", default=DEFAULT_SOFTWARE_TEMPLATE)
    create.add_argument("--lead-account-id")
    create.add_argument("--assignee-type", choices=["PROJECT_LEAD", "UNASSIGNED"], default="UNASSIGNED")
    add_execution_flags(create)

    update = subparsers.add_parser("update", help="Preview or update a project's key or display name")
    update.add_argument("key", help="Current project key")
    update.add_argument("--new-key")
    update.add_argument("--name")
    add_execution_flags(update)

    args = parser.parse_args()
    if args.command == "list":
        command_list()
    elif args.command == "validate":
        command_validate(args.key)
    elif args.command == "create":
        command_create(args)
    elif args.command == "update":
        command_update(args)


if __name__ == "__main__":
    try:
        main()
    except (JiraError, ValueError) as error:
        fail_cleanly(error)
