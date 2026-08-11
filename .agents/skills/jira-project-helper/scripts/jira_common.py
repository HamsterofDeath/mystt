#!/usr/bin/env python3
"""Shared Jira Cloud REST helpers. Never logs credentials or auth headers."""

from __future__ import annotations

import base64
import json
import os
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any


class JiraError(RuntimeError):
    """A Jira configuration or API error safe to show to the user."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@lru_cache(maxsize=None)
def _windows_user_environment(name: str) -> str | None:
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                value, _ = winreg.QueryValueEx(key, name)
                return str(value).strip() or None
        except (FileNotFoundError, OSError):
            return None

    is_wsl = "microsoft" in platform.release().lower() or bool(os.environ.get("WSL_DISTRO_NAME"))
    if not is_wsl:
        return None

    powershell = Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
    if not powershell.exists():
        return None
    result = subprocess.run(
        [
            str(powershell),
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"[Environment]::GetEnvironmentVariable('{name}','User')",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


@lru_cache(maxsize=None)
def _macos_keychain(name: str) -> str | None:
    if sys.platform != "darwin":
        return None
    result = subprocess.run(
        ["security", "find-generic-password", "-a", "jira-project-helper", "-s", name, "-w"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


@lru_cache(maxsize=None)
def _skill_config_file(name: str) -> str | None:
    """Non-secret defaults shipped with the skill in jira_config.json."""
    config_file = Path(__file__).resolve().parent.parent / "jira_config.json"
    try:
        data = json.loads(config_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = data.get(name)
    return str(value).strip() or None if value else None


def config_source(name: str) -> tuple[str | None, str | None]:
    """Return (value, origin) for a config variable; origin is None when unset."""
    value = os.environ.get(name)
    if value:
        return value, "environment"
    value = _skill_config_file(name)
    if value:
        return value, "skill-config-file"
    value = _windows_user_environment(name)
    if value:
        return value, "windows-user-environment"
    value = _macos_keychain(name)
    if value:
        return value, "macos-keychain"
    return None, None


def config_value(name: str, *, required: bool = True) -> str | None:
    value, _ = config_source(name)
    if required and not value:
        raise JiraError(f"Missing required environment variable: {name}")
    return value


def jira_config() -> dict[str, str]:
    return {
        "email": str(config_value("JIRA_EMAIL")),
        "token": str(config_value("JIRA_API_TOKEN")),
        "api_base_url": str(config_value("JIRA_API_BASE_URL")).rstrip("/"),
        "site_url": str(config_value("JIRA_SITE_URL")).rstrip("/"),
        # Not every command needs a default project; require it only where used.
        "project_key": config_value("JIRA_PROJECT_KEY", required=False) or "",
    }


@lru_cache(maxsize=None)
def _repo_project_key() -> str | None:
    """Project key from a `.jira-project` file at the current repo's root."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    candidate = Path(result.stdout.strip()) / ".jira-project"
    try:
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None
    return None


def require_project_key(config: dict[str, str], explicit: str | None = None) -> str:
    """Resolve the project key: --project flag, env var, repo file, keychain default."""
    key = (
        explicit
        or os.environ.get("JIRA_PROJECT_KEY")
        or _repo_project_key()
        or config.get("project_key")
        or ""
    ).strip().upper()
    if not key:
        raise JiraError(
            "No project key: pass --project, add a .jira-project file at the repo root, "
            "or store a default via "
            "security add-generic-password -U -a jira-project-helper -s JIRA_PROJECT_KEY -w <KEY>"
        )
    return key


def jira_request(
    method: str,
    path: str,
    *,
    payload: Any | None = None,
    query: dict[str, Any] | None = None,
    retry_safe_reads: bool = True,
) -> Any:
    config = jira_config()
    url = config["api_base_url"] + "/" + path.lstrip("/")
    if query:
        url += "?" + urllib.parse.urlencode(query, doseq=True)

    # Scoped API tokens authenticate as Bearer against the scoped
    # api.atlassian.com endpoint; classic tokens use Basic email:token.
    if "api.atlassian.com" in config["api_base_url"]:
        authorization = "Bearer " + config["token"]
    else:
        credentials = f'{config["email"]}:{config["token"]}'.encode("utf-8")
        authorization = "Basic " + base64.b64encode(credentials).decode("ascii")
    headers = {
        "Accept": "application/json",
        "Authorization": authorization,
    }
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    # 401/429 responses are rejected before Jira processes the request, so
    # retrying them is safe even for writes. Network errors are only retried
    # for safe reads — a lost write response is ambiguous and never replayed.
    attempts = 8
    can_retry_network = method.upper() == "GET" and retry_safe_reads
    last_network_error: JiraError | None = None
    for attempt in range(attempts):
        request = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                response_body = response.read()
                if not response_body:
                    return None
                return json.loads(response_body.decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code == 429 and attempt + 1 < attempts:
                delay = int(error.headers.get("Retry-After", "2"))
                time.sleep(max(1, min(delay, 60)))
                continue
            # Freshly created scoped tokens intermittently 401 (in bursts) while
            # Atlassian replicates them across edge nodes; retry with backoff.
            if error.code == 401 and attempt + 1 < attempts:
                time.sleep(min(15, 3 * (attempt + 1)))
                continue
            raw = error.read().decode("utf-8", errors="replace")
            message = raw[:2000]
            try:
                parsed = json.loads(raw)
                parts = list(parsed.get("errorMessages", []))
                parts.extend(f"{key}: {value}" for key, value in parsed.get("errors", {}).items())
                if parts:
                    message = "; ".join(str(part) for part in parts)
            except (ValueError, AttributeError):
                pass
            raise JiraError(f"Jira API returned HTTP {error.code}: {message}", status=error.code) from None
        except urllib.error.URLError as error:
            # Transient network failures retry for safe reads only; never replay writes.
            last_network_error = JiraError(f"Could not reach Jira: {error.reason}")
            if can_retry_network and attempt + 1 < attempts:
                time.sleep(2**attempt)
                continue
            raise last_network_error from None

    raise JiraError("Jira request failed after retries")


def adf_from_text(text: str) -> dict[str, Any]:
    paragraphs: list[dict[str, Any]] = []
    for paragraph in text.split("\n\n"):
        content: list[dict[str, Any]] = []
        for index, line in enumerate(paragraph.splitlines() or [""]):
            if index:
                content.append({"type": "hardBreak"})
            if line:
                content.append({"type": "text", "text": line})
        node: dict[str, Any] = {"type": "paragraph"}
        if content:
            node["content"] = content
        paragraphs.append(node)
    return {"type": "doc", "version": 1, "content": paragraphs or [{"type": "paragraph"}]}


def issue_record(issue: dict[str, Any]) -> dict[str, Any]:
    fields = issue.get("fields") or {}
    config = jira_config()
    return {
        "key": issue.get("key"),
        "summary": fields.get("summary"),
        "status": (fields.get("status") or {}).get("name"),
        "assignee": (fields.get("assignee") or {}).get("displayName"),
        "priority": (fields.get("priority") or {}).get("name"),
        "updated": fields.get("updated"),
        "url": f'{config["site_url"]}/browse/{issue.get("key")}',
    }


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def fail_cleanly(error: Exception) -> None:
    print(f"Error: {error}", file=sys.stderr)
    raise SystemExit(1)
