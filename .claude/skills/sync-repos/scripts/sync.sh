#!/usr/bin/env bash
# sync-repos: discover new BLG repositories, then full-sync every local repo
# under the single consolidated workspace root (~/IdeaProjects).
# Per repo: clone if newly created and missing -> auto-commit local changes ->
# fetch --prune -> pull --rebase -> push.
# Handles branches whose remote was renamed/deleted (e.g. master -> main).
# Never force-pushes; aborts and reports conflicting rebases.

set -u

# Never let git block on an interactive credential prompt; fail fast instead.
export GIT_TERMINAL_PROMPT=0

# Single consolidated workspace root: every repository lives directly under it.
# Override by exporting BLG_ROOT; otherwise default to ~/IdeaProjects.
BLG_ROOT="${BLG_ROOT:-$HOME/IdeaProjects}"

ROOTS=("$BLG_ROOT")
COMMIT_MSG="chore: auto-sync local changes"
BLG_OWNER="HamsterofDeath"
# Fixed baseline: only repositories created after this skill update are
# auto-cloned. Override for recovery/testing with BLG_REPO_DISCOVERY_SINCE.
BLG_DISCOVERY_SINCE="${BLG_REPO_DISCOVERY_SINCE:-2026-07-20T14:46:20Z}"

declare -a ROW_NAME=() ROW_BRANCH=() ROW_ACTIONS=() ROW_STATUS=() CLONED_DIRS=()
HAD_PROBLEM=0

add_row() {
  ROW_NAME+=("$1"); ROW_BRANCH+=("$2"); ROW_ACTIONS+=("$3"); ROW_STATUS+=("$4")
}

was_cloned() {
  local candidate="$1" cloned
  [ "${#CLONED_DIRS[@]}" -gt 0 ] || return 1
  for cloned in "${CLONED_DIRS[@]}"; do
    [ "$candidate" = "$cloned" ] && return 0
  done
  return 1
}

repo_present_locally() {
  local remote_name="$1" remote_name_lower gitdir repo origin normalized
  remote_name_lower="$(printf '%s' "$remote_name" | tr '[:upper:]' '[:lower:]')"

  for gitdir in "$BLG_ROOT"/*/.git; do
    [ -d "$gitdir" ] || continue
    repo="${gitdir%/.git}"
    origin="$(git -C "$repo" remote get-url origin 2>/dev/null || true)"
    normalized="$(printf '%s' "${origin%.git}" | tr '[:upper:]' '[:lower:]')"
    case "$normalized" in
      "https://github.com/hamsterofdeath/$remote_name_lower" | \
      "git@github.com:hamsterofdeath/$remote_name_lower")
        return 0
        ;;
    esac
  done
  return 1
}

clone_missing_blg_repos() {
  [ -d "$BLG_ROOT" ] || return

  if ! command -v gh >/dev/null 2>&1; then
    add_row "(BLG discovery)" "-" "-" "discovery-error"
    HAD_PROBLEM=1
    return
  fi

  local token listing
  if ! token="$(gh auth token --hostname github.com --user "$BLG_OWNER" 2>/dev/null)"; then
    add_row "(BLG discovery)" "-" "-" "discovery-error"
    HAD_PROBLEM=1
    return
  fi

  if ! listing="$(
    GH_TOKEN="$token" gh repo list "$BLG_OWNER" \
      --limit 1000 \
      --json name,createdAt \
      --jq ".[] | select(.createdAt > \"$BLG_DISCOVERY_SINCE\") | [.name, .createdAt] | @tsv" \
      2>/dev/null
  )"; then
    unset token
    add_row "(BLG discovery)" "-" "-" "discovery-error"
    HAD_PROBLEM=1
    return
  fi

  local name created_at target clone_url
  while IFS=$'\t' read -r name created_at; do
    [ -n "$name" ] || continue
    repo_present_locally "$name" && continue

    target="$BLG_ROOT/$name"
    clone_url="https://github.com/$BLG_OWNER/$name.git"

    if [ -e "$target" ]; then
      add_row "$name" "-" "created $created_at" "clone-blocked"
      HAD_PROBLEM=1
      continue
    fi

    echo ">> cloning ${clone_url} -> ${target}"
    # Authenticate the HTTPS clone with the gh token (many BLG repos are
    # private) and disable terminal prompts so a credential problem fails
    # fast as clone-error instead of hanging the whole sync.
    if GIT_TERMINAL_PROMPT=0 \
       GIT_CONFIG_COUNT=1 \
       GIT_CONFIG_KEY_0='http.https://github.com/.extraheader' \
       GIT_CONFIG_VALUE_0="Authorization: token ${token}" \
       git clone -q "$clone_url" "$target" 2>/dev/null; then
      CLONED_DIRS+=("$target")
    else
      add_row "$name" "-" "created $created_at" "clone-error"
      HAD_PROBLEM=1
    fi
  done <<< "$listing"
  unset token
}

# Default branch name on the remote (e.g. "main"), via the symref of HEAD.
remote_default_branch() {
  git -C "$1" ls-remote --symref origin HEAD 2>/dev/null \
    | awk '/^ref:/{sub("refs/heads/","",$2); print $2; exit}'
}

sync_repo() {
  local dir="$1" name actions=""
  name="$(basename "$dir")"
  if was_cloned "$dir"; then
    actions="cloned"
  fi

  # Unborn branch (repo has no commits yet) -> nothing to sync.
  if ! git -C "$dir" rev-parse --verify -q HEAD >/dev/null 2>&1; then
    add_row "$name" "(empty)" "${actions:--}" "empty"
    return
  fi

  local branch
  branch="$(git -C "$dir" symbolic-ref --quiet --short HEAD 2>/dev/null)"
  if [ -z "$branch" ]; then
    add_row "$name" "(detached)" "-" "detached"; HAD_PROBLEM=1; return
  fi

  # Must have an 'origin' remote.
  if ! git -C "$dir" remote get-url origin >/dev/null 2>&1; then
    add_row "$name" "$branch" "-" "no-remote"; HAD_PROBLEM=1; return
  fi

  # 1. Auto-commit local changes (git add -A respects .gitignore).
  git -C "$dir" add -A 2>/dev/null
  if ! git -C "$dir" diff --cached --quiet 2>/dev/null; then
    if git -C "$dir" commit -q -m "$COMMIT_MSG" 2>/dev/null; then
      actions="committed"
    else
      add_row "$name" "$branch" "$actions" "error"; HAD_PROBLEM=1; return
    fi
  fi

  # 2. Fetch (prune deletes tracking refs for branches removed on the remote).
  if ! git -C "$dir" fetch -q --prune origin 2>/dev/null; then
    add_row "$name" "$branch" "${actions:--}" "error"; HAD_PROBLEM=1; return
  fi

  # Classify the upstream situation.
  local upstream had_upstream_cfg
  upstream="$(git -C "$dir" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null)"
  had_upstream_cfg="$(git -C "$dir" config --get "branch.$branch.merge" 2>/dev/null)"

  if [ -z "$upstream" ] && [ -n "$had_upstream_cfg" ]; then
    # Branch was tracking a remote branch that no longer exists (renamed/deleted,
    # e.g. master -> main). If the local branch is fully contained in the remote's
    # new default branch, switch to it; otherwise report for manual handling.
    local def
    def="$(remote_default_branch "$dir")"
    if [ -n "$def" ] && git -C "$dir" rev-parse -q --verify "refs/remotes/origin/$def" >/dev/null 2>&1 \
       && git -C "$dir" merge-base --is-ancestor HEAD "origin/$def" 2>/dev/null; then
      if git -C "$dir" checkout -q "$def" 2>/dev/null; then
        git -C "$dir" branch -d "$branch" >/dev/null 2>&1   # safe: -d refuses if unmerged
        actions="${actions:+$actions, }switched $branch->$def"
        branch="$def"
        upstream="$(git -C "$dir" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null)"
      else
        add_row "$name" "$branch" "${actions:--}" "upstream-gone"; HAD_PROBLEM=1
        return
      fi
    else
      add_row "$name" "$branch" "${actions:--}" "upstream-gone"; HAD_PROBLEM=1
      return
    fi
  fi

  # A matching remote branch may exist even when local tracking was never set.
  if [ -z "$upstream" ] \
     && git -C "$dir" rev-parse -q --verify "refs/remotes/origin/$branch" >/dev/null 2>&1; then
    if git -C "$dir" branch --set-upstream-to="origin/$branch" "$branch" >/dev/null 2>&1; then
      upstream="origin/$branch"
    else
      add_row "$name" "$branch" "${actions:--}" "error"; HAD_PROBLEM=1; return
    fi
  fi

  # 3. Pull with rebase when an upstream is present. Local commits are replayed
  # onto the fetched upstream; only unpublished local history is rewritten, so a
  # normal push stays possible. Fast-forwards when simply behind.
  if [ -n "$upstream" ]; then
    local before after ahead_before behind_before
    before="$(git -C "$dir" rev-parse HEAD)"
    read -r ahead_before behind_before < <(
      git -C "$dir" rev-list --left-right --count "HEAD...@{u}" 2>/dev/null
    )
    if git -C "$dir" pull -q --rebase 2>/dev/null; then
      after="$(git -C "$dir" rev-parse HEAD)"
      if [ "$before" != "$after" ]; then
        if [ "${ahead_before:-0}" -gt 0 ] && [ "${behind_before:-0}" -gt 0 ]; then
          actions="${actions:+$actions, }rebased"
        else
          actions="${actions:+$actions, }pulled"
        fi
      fi
    else
      if [ -d "$dir/.git/rebase-merge" ] || [ -d "$dir/.git/rebase-apply" ]; then
        git -C "$dir" rebase --abort >/dev/null 2>&1 || true
        add_row "$name" "$branch" "${actions:--}" "conflict"
      else
        add_row "$name" "$branch" "${actions:--}" "error"
      fi
      HAD_PROBLEM=1
      return
    fi
  fi

  # 4. Push: set upstream if there is none, else push when ahead.
  if [ -z "$upstream" ]; then
    if git -C "$dir" push -q -u origin HEAD 2>/dev/null; then
      actions="${actions:+$actions, }pushed (new upstream)"
    else
      add_row "$name" "$branch" "${actions:--}" "error"; HAD_PROBLEM=1; return
    fi
  else
    local ahead
    ahead="$(git -C "$dir" rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0)"
    if [ "${ahead:-0}" -gt 0 ]; then
      if git -C "$dir" push -q 2>/dev/null; then
        actions="${actions:+$actions, }pushed"
      else
        add_row "$name" "$branch" "${actions:--}" "error"; HAD_PROBLEM=1; return
      fi
    fi
  fi

  if [ -z "$actions" ]; then
    add_row "$name" "$branch" "-" "up-to-date"
  else
    add_row "$name" "$branch" "$actions" "ok"
  fi
}

clone_missing_blg_repos

for root in "${ROOTS[@]}"; do
  [ -d "$root" ] || continue
  for dir in "$root"/*/; do
    [ -d "${dir}.git" ] || continue
    dir="${dir%/}"
    echo ">> ${dir}"
    sync_repo "$dir"
  done
done

echo
echo "================================ SYNC SUMMARY ================================"
printf '%-22s %-22s %-30s %s\n' "REPO" "BRANCH" "ACTIONS" "STATUS"
printf '%-22s %-22s %-30s %s\n' "----" "------" "-------" "------"
for i in "${!ROW_NAME[@]}"; do
  printf '%-22s %-22s %-30s %s\n' \
    "${ROW_NAME[$i]}" "${ROW_BRANCH[$i]}" "${ROW_ACTIONS[$i]}" "${ROW_STATUS[$i]}"
done
echo "============================================================================="

[ "$HAD_PROBLEM" -eq 0 ] || exit 1
exit 0
