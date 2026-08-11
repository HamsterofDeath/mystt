#!/usr/bin/env python3
"""Configure and verify BLG's GitHub credential isolation.

BLG repositories always authenticate as HamsterofDeath through the operating
system's native credential store. The active GitHub CLI account is deliberately
left untouched, so a second GitHub identity can remain active outside ~/BLG.

This script never prints a credential. When --store-token is used, the token is
read with a hidden terminal prompt and sent directly to Git's credential helper.
"""

from __future__ import annotations

import argparse
import getpass
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

ACCOUNT = "HamsterofDeath"
GITHUB_HOST = "github.com"
HOME = Path.home()
BLG_CONFIG = HOME / ".gitconfig-blg"


def run(
    args: list[str],
    *,
    cwd: Optional[Path] = None,
    input_text: Optional[str] = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "Never"
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        input=input_text,
        capture_output=True,
        text=True,
        env=env,
    )


def workspace_root() -> Path:
    """Use an explicit workspace setting before historical default paths."""
    configured = os.environ.get("BLG_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()

    """Prefer the canonical spelling while supporting an older ~/blg clone."""
    canonical = HOME / "BLG"
    legacy = HOME / "blg"
    if canonical.exists():
        return canonical
    if legacy.exists():
        return legacy
    return canonical


def git_exec_path() -> Optional[Path]:
    result = run(["git", "--exec-path"])
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return Path(value) if value else None


def helper_executable(name: str) -> Optional[Path]:
    executable = shutil.which(f"git-credential-{name}")
    if executable:
        return Path(executable)
    exec_path = git_exec_path()
    if exec_path:
        for suffix in ("", ".exe"):
            candidate = exec_path / f"git-credential-{name}{suffix}"
            if candidate.is_file():
                return candidate
    return None


def native_helper() -> tuple[Optional[str], str]:
    system = platform.system()
    if system == "Darwin":
        if helper_executable("osxkeychain"):
            return "osxkeychain", "macOS Keychain"
        return None, "macOS Keychain helper (git-credential-osxkeychain) is missing"

    if system == "Windows":
        if helper_executable("manager"):
            return "manager", "Windows Credential Manager via Git Credential Manager"
        if helper_executable("manager-core"):
            return "manager-core", "Windows Credential Manager via Git Credential Manager Core"
        return None, "Git Credential Manager is missing"

    if system == "Linux":
        executable = helper_executable("libsecret")
        if executable:
            return str(executable), "Secret Service/libsecret"
        for candidate in (
            Path("/usr/lib/git-core/git-credential-libsecret"),
            Path("/usr/share/doc/git/contrib/credential/libsecret/git-credential-libsecret"),
        ):
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate), "Secret Service/libsecret"
        return None, "git-credential-libsecret is missing"

    return None, f"no supported native credential helper for {system}"


def git_config(
    scope: list[str],
    *args: str,
    input_text: Optional[str] = None,
) -> subprocess.CompletedProcess[str]:
    return run(["git", "config", *scope, *args], input_text=input_text)


def config_values(config_file: Path, key: str) -> list[str]:
    result = git_config(["--file", str(config_file)], "--get-all", key)
    if result.returncode not in (0, 1):
        return []
    return result.stdout.splitlines()


def global_include_entries() -> list[tuple[str, str]]:
    result = git_config(
        ["--global"],
        "--get-regexp",
        r"^includeIf\..*\.path$",
    )
    if result.returncode not in (0, 1):
        return []
    entries: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        key, separator, value = line.partition(" ")
        if separator:
            entries.append((key, value.strip()))
    return entries


def resolved_config_path(value: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(value))).resolve()


def canonical_include_key(root: Path) -> str:
    root_text = root.resolve().as_posix().rstrip("/") + "/"
    return f"includeIf.gitdir/i:{root_text}.path"


def include_is_configured(root: Path) -> bool:
    expected = BLG_CONFIG.resolve()
    root_text = root.resolve().as_posix().lower().rstrip("/") + "/"
    for key, value in global_include_entries():
        try:
            same_file = resolved_config_path(value) == expected
        except OSError:
            same_file = False
        normalized_key = key.lower().replace("\\", "/")
        if same_file and root_text in normalized_key:
            return True
    return False


def replace_config_values(config_file: Path, key: str, values: list[str]) -> None:
    git_config(["--file", str(config_file)], "--unset-all", key)
    for value in values:
        result = git_config(["--file", str(config_file)], "--add", key, value)
        if result.returncode != 0:
            raise RuntimeError(f"could not write {key} to {config_file}")


def configure_git(helper: str, root: Path) -> None:
    BLG_CONFIG.parent.mkdir(parents=True, exist_ok=True)

    expected = BLG_CONFIG.resolve()
    wanted_key = canonical_include_key(root)
    for key, value in global_include_entries():
        try:
            same_file = resolved_config_path(value) == expected
        except OSError:
            same_file = False
        if same_file and key.lower() != wanted_key.lower():
            git_config(["--global"], "--unset-all", key)

    result = git_config(["--global"], "--replace-all", wanted_key, str(BLG_CONFIG))
    if result.returncode != 0:
        raise RuntimeError("could not add the conditional BLG Git configuration")

    # The empty helper entry resets helpers inherited from the system/global
    # config (especially `gh auth git-credential`) before the native helper.
    replace_config_values(BLG_CONFIG, "credential.helper", ["", helper])
    replace_config_values(BLG_CONFIG, "credential.username", [ACCOUNT])
    replace_config_values(
        BLG_CONFIG,
        f"credential.https://{GITHUB_HOST}.helper",
        ["", helper],
    )
    replace_config_values(
        BLG_CONFIG,
        f"credential.https://{GITHUB_HOST}.username",
        [ACCOUNT],
    )


def discover_repositories(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    repositories: list[Path] = []
    if (root / ".git").exists():
        repositories.append(root)
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / ".git").exists():
            repositories.append(child)
    return repositories


def origin_url(repo: Path) -> Optional[str]:
    result = run(["git", "-C", str(repo), "remote", "get-url", "origin"])
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def https_url_for_own_ssh_remote(url: str) -> Optional[str]:
    patterns = (
        rf"git@{re.escape(GITHUB_HOST)}:{re.escape(ACCOUNT)}/(.+)",
        rf"ssh://git@{re.escape(GITHUB_HOST)}/{re.escape(ACCOUNT)}/(.+)",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, url, flags=re.IGNORECASE)
        if match:
            return f"https://{GITHUB_HOST}/{ACCOUNT}/{match.group(1)}"
    return None


def normalize_owned_remotes(root: Path) -> list[str]:
    changed: list[str] = []
    for repo in discover_repositories(root):
        url = origin_url(repo)
        if not url:
            continue
        replacement = https_url_for_own_ssh_remote(url)
        if not replacement:
            continue
        result = run(
            ["git", "-C", str(repo), "remote", "set-url", "origin", replacement]
        )
        if result.returncode != 0:
            raise RuntimeError(f"could not update origin in {repo}")
        changed.append(repo.name)
    return changed


def credential_git_args(helper: str) -> list[str]:
    return [
        "git",
        "-c",
        "credential.helper=",
        "-c",
        f"credential.helper={helper}",
        "-c",
        f"credential.https://{GITHUB_HOST}.username={ACCOUNT}",
        "credential",
    ]


def stored_credential_is_present(helper: str) -> bool:
    request = (
        "protocol=https\n"
        f"host={GITHUB_HOST}\n"
        f"username={ACCOUNT}\n\n"
    )
    result = run(credential_git_args(helper) + ["fill"], input_text=request)
    if result.returncode != 0:
        return False

    # Parse only presence and username; never emit or retain the secret value.
    username: Optional[str] = None
    has_password = False
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if not separator:
            continue
        if key == "username":
            username = value
        elif key == "password":
            has_password = bool(value)
    result.stdout = ""
    return username == ACCOUNT and has_password


def store_credential(helper: str) -> None:
    if not sys.stdin.isatty():
        raise RuntimeError("--store-token requires an interactive terminal")
    token = getpass.getpass(
        f"GitHub token for {ACCOUNT} (hidden; stored only in the native keychain): "
    )
    if not token:
        raise RuntimeError("no token entered")
    request = (
        "protocol=https\n"
        f"host={GITHUB_HOST}\n"
        f"username={ACCOUNT}\n"
        f"password={token}\n\n"
    )
    result = run(credential_git_args(helper) + ["approve"], input_text=request)
    token = ""
    request = ""
    if result.returncode != 0:
        raise RuntimeError("the native credential helper rejected the credential")


def remote_problems(root: Path) -> list[str]:
    problems: list[str] = []
    for repo in discover_repositories(root):
        url = origin_url(repo)
        if not url or "github.com" not in url.lower():
            continue
        if https_url_for_own_ssh_remote(url):
            problems.append(f"{repo.name}: own origin still uses SSH ({url})")
            continue
        expected_prefix = f"https://{GITHUB_HOST}/{ACCOUNT}/"
        if url.lower().startswith("https://github.com/") and not url.lower().startswith(
            expected_prefix.lower()
        ):
            problems.append(
                f"{repo.name}: GitHub origin belongs to another owner; left unchanged ({url})"
            )
    return problems


def check_configuration(helper: str, root: Path) -> list[str]:
    problems: list[str] = []
    if not include_is_configured(root):
        problems.append(f"{BLG_CONFIG} is not conditionally included for {root}")

    helper_values = config_values(BLG_CONFIG, "credential.helper")
    if helper_values[-2:] != ["", helper]:
        problems.append(
            f"{BLG_CONFIG} does not reset inherited helpers and select {helper}"
        )

    github_helper_values = config_values(
        BLG_CONFIG, f"credential.https://{GITHUB_HOST}.helper"
    )
    if github_helper_values[-2:] != ["", helper]:
        problems.append(
            f"{BLG_CONFIG} does not isolate github.com with {helper}"
        )

    if config_values(BLG_CONFIG, "credential.username")[-1:] != [ACCOUNT]:
        problems.append(f"{BLG_CONFIG} does not pin username {ACCOUNT}")
    if config_values(
        BLG_CONFIG, f"credential.https://{GITHUB_HOST}.username"
    )[-1:] != [ACCOUNT]:
        problems.append(f"{BLG_CONFIG} does not pin github.com to {ACCOUNT}")

    problems.extend(remote_problems(root))
    if not stored_credential_is_present(helper):
        problems.append(
            f"no native-keychain credential found for {ACCOUNT}@{GITHUB_HOST}"
        )
    return problems


def print_remediation(script: Path) -> None:
    print("\nOne-time remediation:")
    print(f"  python3 {script} --apply")
    print("If the final check says the credential is missing:")
    print(f"  python3 {script} --store-token")
    print("Enter the token only at the hidden terminal prompt, never in chat.")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Use a native OS keychain and the HamsterofDeath identity for Git "
            "operations under ~/BLG without switching the active gh account."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="Verify configuration, remotes, and credential presence (default).",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Configure the native helper and normalize owned GitHub SSH remotes.",
    )
    mode.add_argument(
        "--store-token",
        action="store_true",
        help="Configure, then securely prompt for and store the GitHub token.",
    )
    args = parser.parse_args(argv)
    if not (args.apply or args.store_token):
        args.check = True

    helper, helper_label = native_helper()
    if not helper:
        print(f"ERROR: {helper_label}.")
        if platform.system() == "Linux":
            print(
                "Install and unlock a Secret Service keyring plus "
                "git-credential-libsecret; plaintext credential storage is forbidden."
            )
        return 2

    root = workspace_root()
    print(f"BLG GitHub account: {ACCOUNT}")
    print(f"Workspace: {root}")
    print(f"Credential store: {helper_label} ({helper})")
    print("GitHub CLI active-account selection: unchanged")

    try:
        if args.apply or args.store_token:
            configure_git(helper, root)
            changed = normalize_owned_remotes(root)
            if changed:
                print(f"Normalized HTTPS origin: {', '.join(changed)}")
        if args.store_token:
            store_credential(helper)
    except RuntimeError as error:
        print(f"ERROR: {error}")
        return 2

    problems = check_configuration(helper, root)
    if problems:
        print("\nKeychain setup is not ready:")
        for problem in problems:
            print(f"  - {problem}")
        print_remediation(Path(__file__).resolve())
        return 2

    print(
        f"OK: BLG Git operations are pinned to {ACCOUNT} through "
        f"{helper_label}; no secret was printed."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
