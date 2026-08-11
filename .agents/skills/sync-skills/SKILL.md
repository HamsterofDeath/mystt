---
name: sync-skills
description: Synchronize canonical user-authored skills from $BLG_ROOT/skills into repository-local BLG and VEACT copies, quarantine legacy global copies, and keep Bailian only in Qwen. Also verifies BLG GitHub keychain isolation.
---

# sync-skills

Distribute user-authored skills from the canonical git repository into the
project-local directories where each CLI discovers them. The canonical skills
repository is the only source of truth.

## Contract

- Canonical source: `https://github.com/HamsterofDeath/skills.git`, checked out
  at `$BLG_ROOT/skills`.
- BLG targets: each direct git repo or worktree below `$BLG_ROOT`, in both
  `<repo>/.agents/skills/` and `<repo>/.claude/skills/`.
- Marketing targets: the BLG core set plus marketing-specific skills.
- VEACT targets: `$VEACT_ROOT/.agents/skills/` and
  `$VEACT_ROOT/.claude/skills/`; never each checkout below VEACT.
- Qwen exception: the five `bailian-*` skills are copied only to
  `$HOME/.qwen/skills/`.
- Other user/global skill directories are never destinations. Direct legacy
  copies are moved into `$BLG_ROOT/.skill-quarantine/<timestamp>/`.
- Hidden entries such as Codex's `.system` directory are not touched.

Project and global copies never flow back into the canonical repository. If a
skill needs changing, edit `$BLG_ROOT/skills/<skill>/`, then run this sync.

## When to use

- The user asks to sync, clean up, distribute, or inspect custom skills.
- The user asks why skill catalogs contain duplicate user-authored skills.
- A canonical skill changed and project-local copies need refreshing.
- BLG GitHub keychain isolation needs verification or repair.

## Required workflow

Always execute the script from the canonical repository, even when this skill
was selected through a project-local copy.

1. Run the read-only check and inspect the complete output:

   ```bash
   python3 "$BLG_ROOT/skills/sync-skills/scripts/sync.py" --check
   ```

2. If the user has not already authorized changes, ask before applying.

3. Apply the canonical commit/push, local distribution, and recoverable global
   quarantine:

   ```bash
   python3 "$BLG_ROOT/skills/sync-skills/scripts/sync.py" --apply --yes
   ```

4. Run `--check` again. Completion requires `Planned actions: 0`.

The script validates the secure GitHub configuration before network access. Do
not reimplement its copy, atomic replacement, or quarantine logic inline.

## GitHub identity and keychain

BLG repositories use the `HamsterofDeath` identity without changing the active
GitHub CLI account. Credentials must stay in macOS Keychain, Windows Credential
Manager, or Linux Secret Service; plaintext credential storage is forbidden.

The sync invokes `scripts/configure_github_keychain.py` in check or apply mode.
If a credential is missing, use its hidden terminal prompt:

```bash
python3 "$BLG_ROOT/skills/sync-skills/scripts/configure_github_keychain.py" --store-token
```

Never print a token, place it in a remote URL or command argument, save it in a
repository, or ask the user to paste it into chat. See
`references/github-keychain.md` for setup and troubleshooting.

## Failure rules

- `git pull --ff-only` failures stop the sync. Resolve canonical divergence
  manually; do not overwrite history.
- A push failure leaves the canonical commit local and stops distribution.
- A copy failure stops the global quarantine so recoverable source material is
  not moved after a partial distribution.
- `--no-push` is allowed only when the user explicitly wants a local canonical
  commit.
- Restart CLI sessions after a successful cleanup; an already-open session
  retains the skill catalog injected when that session started.
