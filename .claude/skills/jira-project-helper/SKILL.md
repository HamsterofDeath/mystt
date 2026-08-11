---
name: jira-project-helper
description: Administer Jira Cloud projects and work with tickets through the REST API using bundled safe helper scripts. Use when Codex needs to list, validate, create, rename, or re-key projects; find or inspect issues; create tickets; edit fields; add comments; assign work; or transition tickets while keeping the API token out of commands and logs. Treat "the Kanban board", "our tickets", and dictated speech-to-text variants such as "giraffe" as Jira intent. Understand the custom commands "implement all tickets" and "verify all tickets".
---

# Jira Project Helper

Treat “the Kanban board”, “our tickets”, and dictated variants such as “giraffe”
as references to Jira unless the surrounding context clearly means something
else.

Use the bundled Python scripts for repeatable Jira Cloud operations. They use only the Python standard library and support Windows, WSL, Linux, and macOS.

## Shared ticket workflow

Use these normalized meanings across every project:

- `To Do`: not started.
- `In Development`: actively being implemented. Existing `In Progress` or
  `In Bearbeitung` labels are legacy aliases for this state.
- `Verify`: implemented and waiting for verification. Existing `In Review` is a
  legacy alias for this state.
- `Done`: verified and accepted. Existing `Erledigt` is a localized alias.

Resolve the actual status name from the current project's workflow before
transitioning. Do not silently substitute an unrelated status or create a new
status. If the required state is unavailable, report the project and missing
state instead of claiming that the command completed.

Every ticket description must contain these headings, with ticket-specific
criteria where needed:

```markdown
## Definition of done
- [ ] Requested implementation is complete.
- [ ] Relevant tests and checks pass.

## Definition of verified
- [ ] Acceptance behavior was checked in the target environment.
- [ ] Verification evidence is recorded in the ticket.
```

Preserve existing description content. When a heading is missing, add the
standard section only when its criteria can be determined safely; otherwise
leave the ticket out of the completed state and report the missing definition.

## Review authority

Treat an agent review as sufficient for individual-ticket verification and
closure. Do not wait for, request, or require a human review of an individual
ticket; reserve human review for the completed final product.

## Custom commands

These commands operate only on the currently scoped Jira project/board. Resolve
scope from an explicit project or board reference, the repository's
`.jira-project`, or the active board context. Never interpret `all` as every
Jira project. If no project/board can be resolved, ask for it before changing
anything.

Before the first transition, show the resolved ticket list, status mapping, and
planned actions. The explicit command authorizes that bounded workflow; ask
again only if the scope, ticket set, or required status differs materially from
the preview.

### `implement all tickets`

1. Enumerate tickets currently in `To Do` on the scoped board. Use board order,
   then priority and key as a stable fallback order.
2. Process exactly one ticket at a time; never pre-transition or implement the
   batch in parallel.
3. Transition the current ticket to `In Development`, inspect its description
   and repository context, implement the requested work, and run relevant
   tests or validation.
4. Ensure both Definition of done and Definition of verified sections exist.
   Do not invent acceptance criteria when the ticket is ambiguous.
5. When implementation is complete, transition the ticket to `Verify` (or the
   project's `In Review` alias). Do not transition it to `Done`.
6. If blocked or ambiguous, leave it in `In Development`, record the blocker in
   the ticket when appropriate, report it, and continue only with later tickets
   that can be handled safely.

After each ticket, report its key, implementation result, validation performed,
and whether it was handed to verification or left blocked.

### `verify all tickets`

1. Enumerate tickets currently in `Verify` or its `In Review` alias on the
   scoped board. Do not verify tickets in other states.
2. Process exactly one ticket at a time.
3. Read and check both Definition of done and Definition of verified, inspect
   the implementation, and run the appropriate tests and acceptance checks.
4. If any required check fails or evidence is missing, record the exact gap and
   transition the ticket back to `In Development` (or its `In Progress` /
   `In Bearbeitung` alias).
5. If every definition and check passes, record concise verification evidence
   in the ticket and transition it to `Done` (or `Erledigt`).

Never mark a ticket Done merely because implementation exists. After each
ticket, report the evidence and whether it was closed or returned to
development.

## Configuration

Configuration is resolved per variable, in this order:

1. Environment variable.
2. `jira_config.json` next to this file — non-secret defaults shipped with the skill.
3. On WSL: the Windows user environment.
4. On macOS: the login keychain, items stored as
   `security add-generic-password -a jira-project-helper -s <NAME> -w <value>`.

Variables:

- `JIRA_API_TOKEN` — scoped API token; never print it. Keep it in the keychain only,
  never in `jira_config.json` or any other file.
- `JIRA_EMAIL` — Atlassian account email.
- `JIRA_API_BASE_URL` — scoped endpoint such as `https://api.atlassian.com/ex/jira/<cloudId>`.
- `JIRA_SITE_URL` — human-facing Jira site used for browser links.
- `JIRA_PROJECT_KEY` — optional fallback project key.

The project key is per repository, resolved in this order (except `JIRA_PROJECT_KEY`
itself, which is only a fallback): `--project` flag → `JIRA_PROJECT_KEY` env var →
a `.jira-project` file containing the bare key at the repo root → `JIRA_PROJECT_KEY`
from config. Every repository that maps to a Jira project should commit a
`.jira-project` file with its key.

`jira_config.json` on this machine holds:

- `JIRA_EMAIL` = `brainliftgames@gmail.com`
- `JIRA_API_BASE_URL` = `https://api.atlassian.com/ex/jira/bdde1a26-14bd-4170-a966-ef7dccdf1eb7`
- `JIRA_SITE_URL` = `https://brainliftgames-all-agents.atlassian.net`

The keychain holds only `JIRA_API_TOKEN` (scoped token, stored with `-A` so any
local process can read it without a prompt).

To rotate the token, create a new scoped token at
https://id.atlassian.com/manage-profile/security/api-tokens and run
`security add-generic-password -U -A -a jira-project-helper -s JIRA_API_TOKEN -w <new token>`.

Auth scheme: scoped tokens (`ATATT...` created "with scopes") authenticate as
`Authorization: Bearer` against the scoped `api.atlassian.com` endpoint; the
scripts select Bearer automatically when `JIRA_API_BASE_URL` contains
`api.atlassian.com`, and use classic Basic `email:token` otherwise. The token's
scopes decide which endpoints work — when `/rest/api/3/project/search` is blocked
(HTTP 401/403), the scripts fall back to `GET /rest/api/3/project` automatically.

Do not put the token in source files, command arguments, examples, or git.

## Find tickets

Run from this skill directory:

```bash
python3 scripts/find_ticket.py BLG-1
python3 scripts/find_ticket.py "login failure" --limit 10
python3 scripts/find_ticket.py "status = Open ORDER BY updated DESC" --jql
```

Use an issue key for an exact lookup, plain text for project-scoped text search, or `--jql` for an explicit JQL query.

## Administer projects

Use `project_admin.py` for project reads and writes. List and validation are read-only:

```bash
python3 scripts/project_admin.py list
python3 scripts/project_admin.py validate --key ARROW --key MEALCALC
```

Create and update operations preview by default. A batch create is duplicate-safe: an existing matching key/name is skipped, while key/name conflicts stop the entire batch before any write.

```bash
python3 scripts/project_admin.py create \
  --project "ARROW=Arrow A-Maze" \
  --project "MEALCALC=Meal Calculator"
python3 scripts/project_admin.py create \
  --project "ARROW=Arrow A-Maze" \
  --project "MEALCALC=Meal Calculator" \
  --apply

python3 scripts/project_admin.py update BLG --new-key BTLG
python3 scripts/project_admin.py update BLG --name "BrainLiftGames" --apply
```

The create default is a team-managed Kanban software project, led by the authenticated user, with new work unassigned. Override the template, project type, lead, or assignment behavior only when the user asks.

## Create tickets

The helper previews by default. Show the planned fields to the user and obtain confirmation immediately before adding `--apply` for the live request.

```bash
python3 scripts/create_ticket.py --summary "Example" --description "Details"
python3 scripts/create_ticket.py --summary "Example" --description "Details" --apply
```

Useful options include `--issue-type`, `--priority`, `--labels`, `--assignee-account-id`, `--parent`, and `--project`.

## Update tickets

The helper previews by default. Show the planned operations to the user and obtain confirmation immediately before adding `--apply` for the live request.

```bash
python3 scripts/update_ticket.py BLG-1 --summary "New summary"
python3 scripts/update_ticket.py BLG-1 --comment "Investigation started" --transition "In Progress"
python3 scripts/update_ticket.py BLG-1 --comment "Investigation started" --transition "In Progress" --apply
```

The update helper supports summary, description, priority, labels, assignment, comments, and workflow transitions. Use `--clear-assignee` to unassign a ticket.

## Safety rules

- Treat create, update, comment, assignment, and transition operations as external side effects.
- Keep the default preview behavior before every create or update. Use `--apply` only after confirming the exact target and payload.
- For a bulk project request, reconcile the full intended inventory before applying. Validate every key and compare both existing keys and names so reruns cannot create duplicates.
- Never echo authorization headers, tokens, or the Windows Credential Manager secret.
- Do not broaden project scope unless the user asks. The token inherits the Jira permissions of its Atlassian account.
- Handle HTTP `429` by waiting for `Retry-After`; the shared request helper retries safe reads automatically but does not replay writes.
- Use `scripts/install_machine_environment.ps1` only when the user explicitly wants machine-wide Windows variables and understands that all local processes can read them.

## Validate access

Run the read-only health check as the non-mutating smoke test:

```bash
python3 scripts/doctor.py
```

It reports each config value's origin, verifies the token against `/myself`,
lists reachable project keys, and probes search scope. An exact issue lookup
(`python3 scripts/find_ticket.py <KEY>-1`) works as a targeted check too.
