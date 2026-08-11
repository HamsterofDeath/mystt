---
name: update-aliases
description: Use when the user asks to add, change, or review shell aliases for CLI dev tools (claude, codex, agy, opencode) or per-project launch aliases. Default action on bare /update-aliases is to scan the project roots (~/blg and ~/IdeaProjects) for git repos and add all missing <tool>_<project> aliases to ~/.bash_aliases.
user-invocable: true
---

# update-aliases

Manage shell aliases for CLI dev tools and per-project launchers, following the conventions already established in the dotfiles.

## Where aliases live

- **`~/.bash_aliases`** — all per-project launcher aliases, plus `co`. Grouped in one section per tool (`# Project shortcuts` for codex, `# Claude Code project shortcuts`, `# Antigravity project shortcuts`, `# OpenCode (DeepSeek) project shortcuts`).
- **`~/.bashrc`** — the general tool aliases `cc`, `ag`, `oc` (near line 125). Don't add project aliases here.

Always check BOTH files before adding anything (`grep -n alias ~/.bashrc ~/.bash_aliases`) — a fresh shell sources both, and duplicates/overrides are easy to miss.

## Default action

When invoked with no specific request (bare `/update-aliases`), sync the per-project aliases:

1. List git repos across the project roots — `~/blg` (the main games/tools root) and `~/IdeaProjects`:
   `for r in ~/blg ~/IdeaProjects; do for d in "$r"/*/; do [ -d "$d/.git" ] && echo "$(basename "$d") -> $(readlink -f "$d")"; done; done` — directories without a `.git` are skipped.
2. A repo counts as covered if ANY existing alias points at its path — match by path, not name (e.g. `lights_2026` is covered by `cc_lights` etc.; keep established nicknames, don't add duplicates under the full name). Note `~/blg` and `~/IdeaProjects` can hold same-named repos at different paths (e.g. `skills`); the first one aliased keeps the bare `<tool>_<name>` form — flag the collision rather than silently overwriting.
3. For each uncovered repo, add one alias per *installed* tool (`co`, `cc`, `ag`, `oc`) to the matching section of `~/.bash_aliases`, in the patterns below. Skip a tool that isn't on PATH (e.g. `opencode`) and leave a comment noting it.
4. Only top-level git repos under each root are scanned; nested subprojects are skipped.
5. Remind the user to run `source ~/.bashrc` (or open a new shell).

## Conventions

1. **General tool aliases** — short two-char handle for a CLI tool, with the user's preferred default flags.
   - `cc='claude --dangerously-skip-permissions'`
   - `ag='agy --dangerously-skip-permissions'`
   - `co='codex --dangerously-bypass-approvals-and-sandbox'`
   - `oc='opencode'` (opencode has no skip-permissions flag — leave it bare)

2. **Per-project aliases** — `<tool>_<project>`, lowercase, `cd` into the project then launch the tool (intentionally changes the shell's cwd):
   - `cc_eulerslop='cd /home/hod/blg/eulerslop && claude --dangerously-skip-permissions'`
   - `co_eulerslop='cd /home/hod/blg/eulerslop && codex --dangerously-bypass-approvals-and-sandbox'`
   - `ag_eulerslop='cd /home/hod/blg/eulerslop && agy --dangerously-skip-permissions'`
   - `oc_eulerslop='cd /home/hod/blg/eulerslop && opencode'`
   - Hyphens in repo names are kept verbatim in alias names (e.g. `cc_relax-o-mat`) — bash allows them.
   - `<project>` defaults to the repo directory name; an established nickname (e.g. `lights` for `lights_2026`) stays as is.
   - Use the tool's short handle as the prefix (`oc_`, not `opencode_`).

## How to do it (explicit single-alias requests)

1. Grep both files (see above) to match style and avoid duplicates.
2. Resolve the absolute repo path (e.g. via `git rev-parse --show-toplevel`) and use its directory name as `<project>`.
3. Add the alias to the correct tool section of `~/.bash_aliases` with `Edit` (general tool aliases go in `~/.bashrc` next to `cc`/`ag`/`oc`).
4. Remind the user to run `source ~/.bashrc` (or open a new shell) to pick it up.

## Notes

- Don't invent a skip-permissions flag for tools that lack one — check `--help` if unsure.
- When the naming is ambiguous, confirm the literal alias string with the user rather than guessing.
