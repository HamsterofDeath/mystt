#!/usr/bin/env python3
"""Distribute canonical skills to project-local roots and Qwen-only Bailian.

The git repository at ``$BLG_ROOT/skills`` is the only source of truth. The
script never imports changes from project or user-level copies. It distributes
classified skills into BLG/VEACT project roots, keeps the five Bailian skills
only in Qwen's user skill root, and quarantines other legacy global copies.
"""

from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

HOME = Path.home()
REPO_REMOTE = "https://github.com/HamsterofDeath/skills.git"


def configured_path(name: str) -> Optional[Path]:
    value = os.environ.get(name)
    return Path(value).expanduser().resolve() if value else None


def find_blg_root() -> Path:
    """Resolve BLG_ROOT from the environment or the canonical checkout."""
    configured = configured_path("BLG_ROOT")
    if configured is not None:
        return configured

    script_path = Path(__file__).resolve()
    for parent in script_path.parents:
        candidate = parent / "skills" / "sync-skills" / "scripts" / "sync.py"
        if candidate.is_file():
            return parent

    raise RuntimeError(
        "BLG_ROOT is not set and could not be inferred. Set it to the "
        "directory containing the canonical skills checkout."
    )


BLG_ROOT = find_blg_root()
VEACT_ROOT = configured_path("VEACT_ROOT") or (HOME / "veact")
REPO_ROOT = BLG_ROOT / "skills"
MARKETING_REPO = "marketing"

PROJECT_SKILLS_DIRS = (
    Path(".agents") / "skills",
    Path(".claude") / "skills",
)

# These are discovery roots, not sources or ordinary destinations. Every
# direct, non-hidden skill entry is quarantined during --apply, except for the
# explicit Qwen-only Bailian allowlist below.
GLOBAL_SKILL_ROOTS = {
    "codex": HOME / ".codex" / "skills",
    "claude": HOME / ".claude" / "skills",
    "agents": HOME / ".agents" / "skills",
    "antigravity": HOME / ".gemini" / "config" / "skills",
    "antigravity-legacy": HOME / ".gemini" / "antigravity-cli" / "skills",
    "kimi": HOME / ".kimi-code" / "skills",
    "qwen": HOME / ".qwen" / "skills",
}
GLOBAL_QUARANTINE_ROOT = BLG_ROOT / ".skill-quarantine"
QWEN_LABEL = "qwen"
QWEN_ONLY = {
    "bailian-cli",
    "bailian-finetune",
    "bailian-gen",
    "bailian-managed-agent",
    "bailian-protocol",
}

# Every BLG git repository receives this set in both project discovery roots.
CORE = {
    "android-admob-ads",
    "android-emulator-runner",
    "android-usb-deploy",
    "btlg-android-release-ux",
    "btlg-product-onboarding",
    "elevenlabs-voice-production",
    "jira-project-helper",
    "mobile-game-source-code-review",
    "open-in-browser",
    "open-in-firefox",
    "openclaw-browser",
    "suno-music-workflow",
    "sync-repos",
    "sync-skills",
    "update-aliases",
}

# Marketing receives CORE plus these skills.
MARKETING_EXTRA = {
    "admob-settings",
    "btlg-telegram-announcements",
    "making-of-animation",
    "play-console-release",
    "play-store-aso-launch",
    "social-media-posting",
}

# VEACT uses one root project, not copies inside each checkout below it.
VEACT_SET = {
    "open-in-browser",
    "open-in-firefox",
    "teams-messages",
    "veact-atlassian-review",
    "veact-bastion",
    "veact-frontend-api",
    "veact-frontend-testing",
    "veact-github-pr",
    "veact-hollywood-job-download",
    "veact-lead-seeding",
    "veact-leadcheck",
    "veact-open-tasks",
    "veact-pick-up-ticket",
    "veact-s3-download",
    "veact-staging-ops",
}


def excluded_name(name: str) -> bool:
    return name.startswith(".")


def blg_repos() -> list[Path]:
    """Return direct BLG git repositories and worktrees, except skills."""
    repos: list[Path] = []
    if not BLG_ROOT.is_dir():
        return repos
    for entry in sorted(BLG_ROOT.iterdir()):
        if not entry.is_dir() or excluded_name(entry.name):
            continue
        if entry.resolve() == REPO_ROOT.resolve():
            continue
        if (entry / ".git").exists():
            repos.append(entry)
    return repos


def distribution_roots() -> dict[str, Path]:
    """Map managed labels to project-local skill roots plus Qwen's exception."""
    roots: dict[str, Path] = {}
    for repo in blg_repos():
        for relative in PROJECT_SKILLS_DIRS:
            label = f"blg:{repo.name}:{relative.parts[0]}"
            roots[label] = repo / relative
    if VEACT_ROOT.is_dir():
        for relative in PROJECT_SKILLS_DIRS:
            roots[f"veact:{relative.parts[0]}"] = VEACT_ROOT / relative
    roots[QWEN_LABEL] = GLOBAL_SKILL_ROOTS[QWEN_LABEL]
    return roots


def all_blg_labels(repo_name: Optional[str] = None) -> list[str]:
    labels: list[str] = []
    for repo in blg_repos():
        if repo_name is not None and repo.name != repo_name:
            continue
        labels.extend(
            f"blg:{repo.name}:{relative.parts[0]}"
            for relative in PROJECT_SKILLS_DIRS
        )
    return labels


def all_veact_labels() -> list[str]:
    if not VEACT_ROOT.is_dir():
        return []
    return [f"veact:{relative.parts[0]}" for relative in PROJECT_SKILLS_DIRS]


def target_labels_for(name: str) -> list[str]:
    labels: list[str] = []
    if name in CORE:
        labels.extend(all_blg_labels())
    if name in MARKETING_EXTRA:
        labels.extend(all_blg_labels(MARKETING_REPO))
    if name in VEACT_SET:
        labels.extend(all_veact_labels())
    if name in QWEN_ONLY:
        labels.append(QWEN_LABEL)
    return sorted(set(labels))


def git(
    *args: str,
    check: bool = True,
    quiet: bool = False,
) -> subprocess.CompletedProcess[str]:
    command = ["git", "-C", str(REPO_ROOT), *args]
    result = subprocess.run(command, capture_output=True, text=True)
    if not quiet:
        if result.stdout.strip():
            sys.stdout.write(result.stdout)
        if result.stderr.strip():
            sys.stderr.write(result.stderr)
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed (exit {result.returncode})")
    return result


def current_branch() -> str:
    result = git("symbolic-ref", "--short", "HEAD", check=False, quiet=True)
    return result.stdout.strip() or "main"


def ensure_github_keychain(apply: bool) -> None:
    """Verify or configure BLG's account-scoped native-keychain credential."""
    script = Path(__file__).with_name("configure_github_keychain.py")
    if not script.is_file():
        raise RuntimeError(f"GitHub keychain setup script is missing: {script}")
    mode = "--apply" if apply else "--check"
    result = subprocess.run([sys.executable, str(script), mode])
    if result.returncode != 0:
        raise RuntimeError(
            "BLG GitHub keychain preflight failed. Follow the remediation above, "
            "then re-run sync."
        )


def ensure_repo(apply: bool) -> None:
    """Fetch canonical state and fast-forward it only during --apply."""
    if not (REPO_ROOT / ".git").is_dir():
        if not apply:
            raise RuntimeError(
                f"canonical checkout is missing: {REPO_ROOT}; run --apply to clone it"
            )
        print(f"Cloning {REPO_REMOTE} -> {REPO_ROOT}")
        REPO_ROOT.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "clone", REPO_REMOTE, str(REPO_ROOT)],
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            sys.stdout.write(result.stdout)
        if result.stderr.strip():
            sys.stderr.write(result.stderr)
        if result.returncode != 0:
            raise RuntimeError(f"git clone failed (exit {result.returncode})")
        return

    origin = git("remote", "get-url", "origin", check=False, quiet=True)
    if apply:
        if origin.returncode != 0:
            git("remote", "add", "origin", REPO_REMOTE)
        elif origin.stdout.strip() != REPO_REMOTE:
            git("remote", "set-url", "origin", REPO_REMOTE)
        fetched = git("fetch", "origin", check=False)
    else:
        fetched = git(
            "fetch",
            REPO_REMOTE,
            "+refs/heads/*:refs/remotes/origin/*",
            check=False,
        )
    if fetched.returncode != 0:
        raise RuntimeError(
            "git fetch failed; verify the HamsterofDeath HTTPS credential for "
            f"{REPO_REMOTE}, then re-run sync"
        )
    if not apply:
        return

    branch = current_branch()
    remote_branch = git(
        "rev-parse",
        "--verify",
        "--quiet",
        f"refs/remotes/origin/{branch}",
        check=False,
        quiet=True,
    )
    if remote_branch.returncode != 0:
        return
    pulled = git("pull", "--ff-only", check=False)
    if pulled.returncode != 0:
        raise RuntimeError(
            "git pull --ff-only failed; resolve the canonical repository "
            "divergence manually, then re-run sync"
        )


def repo_dirty() -> bool:
    if not (REPO_ROOT / ".git").is_dir():
        return False
    return bool(git("status", "--porcelain", check=False, quiet=True).stdout.strip())


def repo_skill_dirs() -> dict[str, Path]:
    skills: dict[str, Path] = {}
    if not REPO_ROOT.is_dir():
        return skills
    for entry in sorted(REPO_ROOT.iterdir()):
        if excluded_name(entry.name) or not entry.is_dir():
            continue
        if (entry / "SKILL.md").is_file():
            skills[entry.name] = entry
    return skills


def _dircmp_differs(comparison: filecmp.dircmp) -> bool:
    if (
        comparison.left_only
        or comparison.right_only
        or comparison.funny_files
        or comparison.diff_files
    ):
        return True
    _, mismatch, errors = filecmp.cmpfiles(
        comparison.left,
        comparison.right,
        comparison.common_files,
        shallow=False,
    )
    if mismatch or errors:
        return True
    return any(_dircmp_differs(child) for child in comparison.subdirs.values())


def trees_differ(left: Path, right: Path) -> bool:
    if not left.is_dir() or not right.is_dir():
        return True
    return _dircmp_differs(
        filecmp.dircmp(str(left), str(right), ignore=[".git", ".DS_Store"])
    )


def validate_classification(skills: dict[str, Path]) -> None:
    classified = CORE | MARKETING_EXTRA | VEACT_SET | QWEN_ONLY
    missing = sorted(classified - set(skills))
    if missing:
        raise RuntimeError(
            "classified skills are missing from the canonical repository: "
            + ", ".join(missing)
        )
    overlap = sorted(QWEN_ONLY & (CORE | MARKETING_EXTRA | VEACT_SET))
    if overlap:
        raise RuntimeError(
            "Qwen-only skills must not be project-distributed: " + ", ".join(overlap)
        )


@dataclass(frozen=True)
class CopyAction:
    skill: str
    src: Path
    dest: Path
    dest_label: str
    reason: str


@dataclass(frozen=True)
class GlobalEntry:
    root_label: str
    path: Path


def build_plan(
    skills: dict[str, Path],
    roots: dict[str, Path],
) -> tuple[list[CopyAction], list[dict[str, object]]]:
    actions: list[CopyAction] = []
    rows: list[dict[str, object]] = []
    for name, canonical in skills.items():
        labels = target_labels_for(name)
        needed = 0
        for label in labels:
            destination = roots[label] / name
            if destination.is_symlink() or trees_differ(canonical, destination):
                reason = "missing" if not destination.exists() else "canonical differs"
                actions.append(
                    CopyAction(name, canonical, destination, label, reason)
                )
                needed += 1
        if name in QWEN_ONLY:
            scope = "qwen-only"
        elif labels:
            scope = "project-local"
        else:
            scope = "canonical-only"
        rows.append(
            {
                "skill": name,
                "scope": scope,
                "targets": len(labels),
                "copies": needed,
            }
        )
    return actions, rows


def global_skill_entries() -> list[GlobalEntry]:
    """Find globally discoverable skills that violate the allowlist."""
    found: list[GlobalEntry] = []
    for label, root in GLOBAL_SKILL_ROOTS.items():
        if not root.is_dir():
            continue
        try:
            entries = sorted(root.iterdir())
        except OSError:
            continue
        for entry in entries:
            if excluded_name(entry.name):
                continue
            if label == QWEN_LABEL and entry.name in QWEN_ONLY:
                continue
            try:
                is_skill = (entry / "SKILL.md").is_file()
            except OSError:
                is_skill = False
            if is_skill:
                found.append(GlobalEntry(label, entry))
    return found


def print_plan(
    rows: list[dict[str, object]],
    copies: list[CopyAction],
    globals_to_quarantine: list[GlobalEntry],
) -> None:
    print("\nCanonical distribution plan")
    print(f"{'skill':<32} {'scope':<15} {'targets':>7} {'copies':>7}")
    print("-" * 65)
    for row in rows:
        print(
            f"{row['skill']:<32} {row['scope']:<15} "
            f"{row['targets']:>7} {row['copies']:>7}"
        )
    print("-" * 65)

    copy_counts = Counter(action.dest_label.split(":")[0] for action in copies)
    if copy_counts:
        rendered = ", ".join(
            f"{label}={count}" for label, count in sorted(copy_counts.items())
        )
        print(f"Copy actions by scope: {rendered}")

    global_counts = Counter(entry.root_label for entry in globals_to_quarantine)
    if global_counts:
        rendered = ", ".join(
            f"{label}={count}" for label, count in sorted(global_counts.items())
        )
        print(f"Legacy global copies to quarantine: {rendered}")

    total = len(copies) + len(globals_to_quarantine)
    print(f"Planned actions: {total}")


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def atomic_replace(src: Path, dest: Path) -> None:
    """Replace one destination atomically, restoring it on promotion failure."""
    if not src.is_dir():
        raise RuntimeError(f"source is not a directory: {src}")
    parent = dest.parent
    parent.mkdir(parents=True, exist_ok=True)
    stamp = f"{os.getpid()}.{int(time.time() * 1000)}"
    staging = parent / f"{dest.name}.tmp.{stamp}"
    backup = parent / f"{dest.name}.old.{stamp}"

    if shutil.which("rsync"):
        subprocess.run(
            [
                "rsync",
                "-a",
                "--delete",
                "--exclude",
                ".git",
                "--exclude",
                ".DS_Store",
                f"{src}/",
                f"{staging}/",
            ],
            check=True,
        )
    else:
        shutil.copytree(
            src,
            staging,
            symlinks=False,
            ignore=shutil.ignore_patterns(".git", ".DS_Store"),
        )

    had_backup = False
    if dest.is_symlink() or dest.exists():
        os.rename(dest, backup)
        had_backup = True
    try:
        os.rename(staging, dest)
    except Exception:
        if had_backup and not dest.exists():
            os.rename(backup, dest)
        remove_path(staging)
        raise
    if had_backup:
        remove_path(backup)


def commit_and_push(do_push: bool) -> None:
    """Commit canonical edits before distributing them anywhere else."""
    git("add", "-A")
    status = git("status", "--porcelain", check=False, quiet=True).stdout.strip()
    if not status:
        print("\nCanonical repo: nothing to commit.")
        return

    summary = "sync: enforce repo-local skills and Qwen-only Bailian"
    print(f"\nCanonical repo: committing - {summary}")
    git("commit", "-m", summary)
    if not do_push:
        print("Canonical repo: --no-push set; commit remains local.")
        return

    branch = current_branch()
    print(f"Canonical repo: pushing {branch} -> origin")
    pushed = git("push", "-u", "origin", branch, check=False)
    if pushed.returncode != 0:
        raise RuntimeError(
            "git push failed; the commit remains local and distribution was not run"
        )


def distribute(actions: list[CopyAction]) -> int:
    failures = 0
    for action in actions:
        try:
            atomic_replace(action.src, action.dest)
        except Exception as error:
            failures += 1
            print(
                f"FAILED copy {action.skill} -> {action.dest} "
                f"({action.reason}): {error}"
            )
    print(f"Distributed {len(actions) - failures}/{len(actions)} skill copies.")
    return failures


def quarantine_global_entries(entries: list[GlobalEntry]) -> tuple[int, Path]:
    """Move legacy globals to a timestamped, recoverable location."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    quarantine = GLOBAL_QUARANTINE_ROOT / stamp
    moved = 0
    counts: Counter[str] = Counter()
    for entry in entries:
        destination = quarantine / entry.root_label / entry.path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(entry.path), str(destination))
        except Exception as error:
            print(f"FAILED quarantine {entry.path}: {error}")
            continue
        moved += 1
        counts[entry.root_label] += 1
    rendered = ", ".join(
        f"{label}={count}" for label, count in sorted(counts.items())
    )
    print(f"Quarantined {moved}/{len(entries)} legacy global copies: {rendered}")
    if moved:
        print(f"Recoverable quarantine: {quarantine}")
    return moved, quarantine


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Distribute canonical skills to BLG/VEACT project roots, keep "
            "Bailian only in Qwen, and quarantine other global copies."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true", help="Dry run (default); no file changes."
    )
    mode.add_argument(
        "--apply", action="store_true", help="Pull, commit, distribute, quarantine."
    )
    parser.add_argument("--yes", action="store_true", help="Skip confirmation.")
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Commit canonical changes locally without pushing.",
    )
    args = parser.parse_args(argv)
    if not args.apply:
        args.check = True

    try:
        ensure_github_keychain(apply=args.apply)
        ensure_repo(apply=args.apply)
        skills = repo_skill_dirs()
        validate_classification(skills)
    except RuntimeError as error:
        print(f"ERROR: {error}")
        return 2

    roots = distribution_roots()
    copies, rows = build_plan(skills, roots)
    globals_to_quarantine = global_skill_entries()
    print_plan(rows, copies, globals_to_quarantine)

    if args.check:
        return 0
    if not copies and not globals_to_quarantine and not repo_dirty():
        print("\nNothing to apply.")
        return 0

    if not args.yes:
        try:
            answer = input("\nApply this plan? [y/N] ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in {"y", "yes"}:
            print("Aborted.")
            return 1

    try:
        commit_and_push(do_push=not args.no_push)
    except RuntimeError as error:
        print(f"Canonical repo: {error}")
        return 2

    failures = distribute(copies)
    if failures:
        print("Global quarantine skipped because distribution had failures.")
        return 2

    moved, _ = quarantine_global_entries(globals_to_quarantine)
    if moved != len(globals_to_quarantine):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
