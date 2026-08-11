# BLG GitHub keychain standard

Use this standard on every machine that synchronizes or edits BrainLift Games
repositories.

## Contract

- The BLG workspace is `~/BLG`.
- BLG GitHub remotes use HTTPS and the `HamsterofDeath` owner, for example
  `https://github.com/HamsterofDeath/skills.git`.
- Git operations below `~/BLG` authenticate as `HamsterofDeath`.
- The other GitHub account may remain active in GitHub CLI. Never run
  `gh auth switch` as part of BLG setup.
- Credentials live only in the operating system's native secret store:
  - macOS: Keychain via `git-credential-osxkeychain`
  - Windows: Windows Credential Manager via Git Credential Manager
  - Linux: an unlocked Secret Service keyring via `git-credential-libsecret`
- Never use `credential.helper store`, put a token in a remote URL, save a token
  in the repository, pass a token as a command-line argument, or ask the user to
  paste a token into chat.

The isolation is implemented with a conditional include in the user's global Git
configuration. Only repositories under `~/BLG` load `~/.gitconfig-blg`; that file
resets any inherited credential helper (including GitHub CLI's helper), selects
the native keychain, and pins the GitHub username to `HamsterofDeath`. Other
repositories and the active GitHub CLI account are unaffected.

## Setup and verification

From an existing copy of this skill, run:

```bash
python3 ~/BLG/marketing/.agents/skills/sync-skills/scripts/configure_github_keychain.py --apply
```

The command configures the conditional Git include and safely converts
`git@github.com:HamsterofDeath/...` origins directly below `~/BLG` to HTTPS. It
does not change remotes owned by another account.

If the check reports that the credential is missing, run:

```bash
python3 ~/BLG/marketing/.agents/skills/sync-skills/scripts/configure_github_keychain.py --store-token
```

The second command asks for the token through a hidden terminal prompt and sends
it directly to Git's native credential helper. The token needs read/write access
to the BLG repositories that the machine must synchronize. Create or authorize
it in the browser if necessary, but enter it only at the hidden terminal prompt.

Verify at any time with:

```bash
python3 ~/BLG/marketing/.agents/skills/sync-skills/scripts/configure_github_keychain.py --check
```

The check confirms the conditional configuration, native helper, pinned username,
stored-credential presence, and BLG GitHub origin ownership. It reports only
metadata and never prints the stored secret.

When an agent runs inside a restricted sandbox, the operating system may deny
keychain access even though the credential exists. In that case, rerun the exact
check with temporary permission to access the native keychain. Do not replace the
native helper with GitHub CLI or plaintext storage to work around the sandbox.

## New-machine bootstrap

1. Install Git. On Windows, include Git Credential Manager. On Linux, install
   `git-credential-libsecret` and ensure the desktop Secret Service keyring is
   running and unlocked.
2. Put the synchronized `sync-skills` skill on the machine. If the private skills
   repository cannot yet be cloned, copy only this skill from another trusted
   machine, then run its keychain setup script.
3. Run `--store-token` once.
4. Clone the canonical repository:

   ```bash
   mkdir -p ~/BLG
   git clone https://github.com/HamsterofDeath/skills.git ~/BLG/skills
   ```

5. Run `--check`, then `/sync-skills`.

If a Linux machine has no usable encrypted Secret Service keyring, stop and
install/unlock one. Do not fall back to Git's plaintext credential store.

## Troubleshooting

- `no native-keychain credential found`: run `--store-token` in an interactive
  terminal. A browser may be used to create or authorize the token.
- `own origin still uses SSH`: run `--apply`; same-owner SSH origins are converted
  to HTTPS so the conditional keychain setup is actually used.
- `origin belongs to another owner`: inspect the repository. The script leaves it
  unchanged because changing repository ownership is not a safe assumption.
- Authentication still uses the other account: run `--apply` again and verify
  that the repository is inside `~/BLG`. Do not solve it by switching the global
  GitHub CLI account.
