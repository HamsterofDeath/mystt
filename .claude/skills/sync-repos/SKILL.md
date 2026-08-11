---
name: sync-repos
description: Use when the user says "synchronize repository", "synchronize repositories", "sync repo(s)", "sync all repos", "pull everything", "update all repos", or otherwise asks to clone missing repositories and commit, reconcile, and push repository work. Discover and clone newly created in-scope remote repositories that are absent locally, then full-sync every repository by committing local changes, fetching, integrating remote changes by rebasing local commits onto the upstream (merging only when a rebase is unsafe), resolving ordinary conflicts, and pushing. Preserve all work, follow repository policy, and never force-push. Stop only for an unresolvable conflict or missing repository authority. Invoke with /sync-repos.
---

# sync-repos

Full-sync every in-scope Git repository. For BrainLift Games, scan immediate Git
children under `$BLG_ROOT`, the single consolidated workspace root where every
repository now lives directly. It defaults to `/home/hod/IdeaProjects` (the
primary Linux workspace); export `$BLG_ROOT` to point at a different root per
machine (e.g. `~/BLG` on macOS). There is no separate `~/blg` scan — one root
holds everything.

The phrase **synchronize repository** is an explicit instruction to perform the
complete operation: discover and clone new remote repositories, commit local
work, fetch and reconcile remote work, resolve ordinary conflicts, and push the
result. It is not a read-only status request.

## Required interpretation

- Singular wording means the repository currently in scope.
- Plural, `all`, or `everything` means every immediate-child repository in the
  named workspace roots.
- For plural BrainLift Games synchronization, first query repositories owned by
  `HamsterofDeath` using that account's existing GitHub CLI credential without
  switching the globally active account. Clone every missing repository created
  after `2026-07-20T14:46:20Z` into `$BLG_ROOT` using an owner-qualified HTTPS URL.
  This fixed baseline intentionally leaves older, intentionally absent
  repositories alone while ensuring repositories added from this update onward
  are discovered automatically. `BLG_REPO_DISCOVERY_SINCE` may override the
  baseline for recovery or testing.
- Treat a remote as already present when any immediate local BLG repository has
  its `origin`, even if its directory name differs. If the expected clone path
  already exists but is not that repository, report `clone-blocked` and do not
  overwrite it.
- The request authorizes staging and committing all non-ignored tracked and
  untracked changes in those repositories. Inspect the diff and choose a
  meaningful commit message when practical; the helper's fixed fallback message
  is acceptable for an unattended bulk sync.
- Rebase is the default integration strategy: local, unpublished commits are
  replayed onto the fetched upstream, which rewrites no shared history and
  leaves a normal push possible. Use a normal merge instead only when the
  repository's documented policy forbids rebasing or the rebase is unsafe.
- Resolve compatible text conflicts while preserving both local and remote
  intent. Run relevant checks, commit the merge, and continue to push.
- Stop only when a conflict cannot be resolved without a product decision,
  destructive data loss, missing credentials, an unknown remote/upstream, or
  another genuine authority gap.
- Never create a feature branch or pull request for a normal synchronization.
- Never force-push.

Under `$BLG_ROOT`, preserve the workspace contract: work directly on
`main`, use only `HamsterofDeath` owner-qualified origins and credentials, and
leave the BLG pre-push guard enabled.

## What it does

Run the bundled helper script from the loaded skill directory. In the canonical
synchronized clone:

```bash
bash "$BLG_ROOT/marketing/.agents/skills/sync-repos/scripts/sync.sh"
```

For each repo, in order:

0. **Discover and clone** — list all repositories owned by `HamsterofDeath`
   created after the fixed baseline, including private repositories visible to
   that account, and clone missing ones into `$BLG_ROOT`. The account-specific
   `gh auth token --user HamsterofDeath` lookup does not change the active
   GitHub CLI account. Newly cloned repositories immediately continue through
   the normal synchronization checks.
1. **Branch** — resolve current branch. Detached HEAD → report `detached`, skip
   (no commit, no push).
2. **Commit** — `git add -A` (respects `.gitignore`); if anything is staged,
   commit with the fixed message `chore: auto-sync local changes`.
3. **Fetch** — `git fetch --prune origin`. No `origin` remote → report
   `no-remote`, skip. Empty repo (no commits) → report `empty`, skip.
4. **Renamed/deleted upstream** — if the branch was tracking a remote branch that
   no longer exists (e.g. the remote default was renamed `master`→`main`) and the
   local branch is fully contained in the remote's new default branch, switch to
   it (`switched master->main`) and delete the now-stale local branch (safe
   `git branch -d`, refuses if unmerged). If the local branch has unique commits,
   report `upstream-gone` for manual handling — no push.
5. **Pull and rebase** — if the branch has an upstream, run `git pull --rebase`.
   Behind branches fast-forward; diverged branches have their local,
   unpublished commits replayed onto the fetched upstream. This is the helper's
   default; use a merge only where repository policy forbids rebasing. If the
   helper encounters conflicts, it aborts the rebase and reports `conflict`;
   the agent must then perform the conflict-resolution follow-up
   below instead of treating that row as the final result.
6. **Push** — push the synchronized branch. If the branch has no upstream and
   never did, use `git push -u origin HEAD` to create and track it (e.g.
   `marble-maze` on `game-improvements`).

It prints a per-repo `REPO | BRANCH | ACTIONS | STATUS` summary table at the end.
Statuses: `ok`, `up-to-date`, `empty`, `conflict`, `upstream-gone`, `no-remote`,
`detached`, `error`, `discovery-error`, `clone-blocked`, `clone-error` (actions
seen: `cloned`, `committed`, `pulled`, `rebased`, `pushed`, `switched X->Y`). The
script exits non-zero if discovery, cloning, or any repository hits a problem,
so problems stand out. Relay the summary table to the user and call out any
non-`ok`/`up-to-date` rows.

## Finish incomplete rows

Do not treat the helper's non-zero exit as the end of synchronization. For each
actionable row:

1. **`conflict`** — inspect the repository's policy and current operation.
   Continue a safe merge or rebase while preserving compatible local and remote
   work, run relevant checks, stage the resolutions, finish the integration, and
   push it. If the selected strategy is unsafe, abort it and retry with the safe
   alternative. Stop only if a real product decision or destructive choice is
   required.
2. **`upstream-gone`** — inspect the remote default branch. If it contains the
   current branch's history, switch to that default branch, carry over any unique
   local commit, delete the stale local branch safely, and push.
3. **`error`** — inspect the failed repository, correct a transient or ordinary
   Git error when safe, and retry its pull/merge/push sequence.
4. **`discovery-error`** — verify the `HamsterofDeath` GitHub CLI credential and
   network access, then rerun discovery without switching to another account.
5. **`clone-error`** — inspect authentication, network access, and the remote
   URL, then retry the owner-qualified HTTPS clone.
6. **`clone-blocked`** — inspect the existing target path. Do not overwrite,
   delete, or relocate it without user direction.
7. **`no-remote`, `detached`, or `empty`** — report the condition. Do not invent a
   remote, choose a branch, or create an initial commit without user direction.

After the follow-up work, rerun the helper. Synchronization is complete when
every repository with an upstream reports zero ahead and zero behind, with no
merge in progress and no non-ignored working-tree changes. Clearly report any
repository that remains unsynchronized.

## Safety constraints

- **Never force-push.** Do not rebase already-published or shared commits when
  doing so would rewrite remote history. Diverged histories are integrated with
  the safe strategy available, and compatible conflicts are resolved.
- `git add -A` respects each repo's `.gitignore`, so already-ignored build
  artifacts stay uncommitted.
- The commit message is fixed and carries no date/name suffix.

## Note

Since 2026-08-07 the maintained source lives project-local at
`$BLG_ROOT/marketing/.agents/skills/sync-repos/`, not in the skills hub repo.
It is no longer part of the `/sync-skills` mirror set; edit it in place in the
marketing repository.
