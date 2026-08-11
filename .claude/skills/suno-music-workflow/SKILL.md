---
name: suno-music-workflow
description: Create, remix, identify, and download Suno music assets for game/app projects. Use when the user asks Codex to generate songs in Suno, remix a base song into variants, collect Suno song IDs, download Suno tracks, batch download generated songs, or specifically use the user's logged-in Windows Firefox session for Suno downloads.
---

# Suno Music Workflow

## Overview

Use this skill for two connected tasks: creating Suno music variants through Chrome/OpenClaw, and downloading generated tracks through the logged-in Windows Firefox UI. Treat Suno WAV downloads as masters; encode app-ready MP3s from those WAVs afterward.

Always work in the correct game workspace. Each game has its own Suno workspace/library, manifests, downloads, and app asset targets. Before generating, remixing, downloading, or packaging music, identify the target game from the user's request or the current repo, then use that exact workspace consistently:

- Pass the matching `--workspace <game-workspace>` value to Suno automation scripts such as `suno_generate.cjs` and `suno_cover.cjs`.
- Store manifests, candidate notes, source WAVs, encoded MP3s, and final app assets under that game's repo or documented asset directory, not another game's workspace.
- If the target game/workspace is ambiguous, inspect the current repo and nearby project naming first. Ask only if it cannot be determined safely.
- Do not reuse another game's Suno workspace as a convenience, even for temporary tests; one game equals one workspace.

## Song Creation

Use `openclaw-browser` for Suno UI creation. Open `https://suno.com/create` and verify the user is logged in before generating. If the account state is unclear, inspect the page for the profile/account marker rather than asking immediately.

Always enable Suno's `Instrumental` option before generating or covering/remixing music for BTLG music requests. Do this even when the prompt already says `no vocals`, and re-check the setting after switching modes, selecting a source clip, or reloading the create page.

Recommended creation and link collection sequence:

1. Create one instrumental base theme first.
2. Wait until Remix/Cover is available for one strong base result.
3. Attach that base result as the remix/cover source.
4. Generate per-mode variants from the same base motif.
5. For each generated clip, capture the `/song/<uuid>` links in Chrome/OpenClaw before moving on. Chrome/OpenClaw is the source of truth for link discovery.
6. Pass those links or UUIDs to the Firefox download workflow. Do not rely on the direct song page's top player to identify the clip, because cover/remix pages can expose the source track in that player.

For repeatable generation through the logged-in OpenClaw Chrome session, use:

```bash
node /home/hod/.codex/skills/suno-music-workflow/scripts/suno_generate.cjs \
  --workspace 3xscap3 \
  --title "Primary Motion Study" \
  --prompt "instrumental only, no vocals, no lyrics, no voice. ..."
```

### Remix And Cover Variants

When the user asks for variants, difficulty grades, or per-mode arrangements that should share a motif, make a base track first and then use Suno's visible `Remix clip` or `Cover` workflow for the variants. Do not create those variants as unrelated fresh songs unless the user explicitly asks for independent takes.

- Prefer `Remix clip` for difficulty variants when the arrangement, tempo, density, instrumentation, or energy should change while preserving the base identity.
- Prefer `Cover` when the request emphasizes keeping the composition or motif recognizable while changing surface style, instrumentation, or mood.
- For mode or difficulty bands, use one base per mode, then create 4-5 remix/cover variants from that mode's selected base.
- Capture the selected base `/song/<uuid>` and every variant `/song/<uuid>` in the manifest, with fields that identify `source_id`, `variant_type`, mode, and difficulty band.
- After clicking `Remix clip` or `Cover`, verify the create form shows the chosen source clip before generating. If the source marker is not visible, stop and reselect the source from the clip's own card/list row.
- For cover/remix pages, collect the variant link from the generated card/list row, not only from the top player, because the top player can still reference the source clip.
- Title variants explicitly while keeping the titles abstract, for example `Primary Motion Study`, `Dense Motion Study`, or `Quiet Motion Study`, so source and variants can be searched and downloaded later without feeding Suno product names or genre shortcuts.

Use the cover/remix automation script instead of hand-clicking when possible:

```bash
node /home/hod/.codex/skills/suno-music-workflow/scripts/suno_cover.cjs \
  --mode cover \
  --source <source-song-id-or-url> \
  --title "Primary Motion Study Cover" \
  --prompt "instrumental only, no vocals, no lyrics, no voice. ..."
```

`--mode cover` preserves the source composition/motif more strongly while changing surface style. `--mode remix` gives Suno more freedom to change arrangement, density, energy, and structure.

Verify the navigation before spending credits, especially after any Suno UI change:

```bash
node .../suno_cover.cjs --source <id> --title "..." --prompt "..." --dry-run
```

`--dry-run` opens the menu, reaches the create form, selects the workspace, and fills the title and prompt, but does not click Create. Add `SUNO_DEBUG=1` to trace the menu decisions to stderr.

### Suno v5.5 UI notes

Verified 2026-07-28 against the live UI. These are the traps the automation had to be fixed for; expect to re-check them whenever Suno ships a redesign.

- There is no longer a `Remix` **action**. The button labelled `Remix` is a *menu opener*, and the menu items are `Cover`, `Extend`, `Reuse Prompt`, `Reverse`, `Adjust Speed`. Both `--mode cover` and `--mode remix` therefore land on the same Cover form; the modes now differ only in how much freedom the prompt text gives Suno. Keep using `--mode remix` for arrangement-level variants — the distinction still carries into the prompt.
- The `Remix` pill mounts at the foot of the right-hand panel, so it appears only **after** the async "Similar" list has loaded, roughly 7 s in. Do not treat "some overflow button exists" as page-ready: every row of the Similar list has one.
- The action menu is **not** rendered into a portal — items are plain `<button data-react-aria-pressable>` elements inside anonymous divs, with no `role="menu"` ancestor to scope to. Distinguish menu items from the opener by marking the opener, not by container.
- Suno installs a `data-base-ui-inert` presentation overlay that intercepts real mouse events. Playwright's trusted clicks time out against menus and the workspace panel; DOM `.click()` is what works.
- The create form is React-controlled. Use the native value setter plus `input`/`change` events; `fill()` can leave the visible text set while the internal state stays empty, so the generation silently uses the previous prompt.
- The styles textarea is **not** the first visible textarea. Identify it by its genre-list placeholder or by the prompt a cover inherits from its source, then read the value back to confirm it took.
- Workspace selection happens through the right-hand **Workspaces** panel, not the create form. The `Save to...` chip only focuses itself when clicked; clicking the panel row is what rebinds the save target.
- A cover inherits its source's instrumental setting and v5.5 states that as inline copy ("This song will be instrumental, with no vocals or lyrics.") rather than a checked radio. Treat that copy as authoritative.
- Baseline the song-link list on the **create page** before clicking Create. The song page links to only a handful of songs while the create page lists the whole workspace, so baselining on the song page makes every existing workspace track look new.

Prompting rules:

- Treat reference-free prompting as a hard rule for every Suno generation,
  including Extend, Cover, and Remix. Each prompt must stand alone and describe
  only the desired music. Do not mention or allude to a source track, attached
  audio, previous/current version, candidate, continuation, extension, retained
  motif, game, app, menu, room, level, product, or any other external context.
  Express source relationships only through the selected Suno UI action and
  record them in the manifest, never in the prompt.
- Do not use relational wording such as `continue`, `preserve`, `retain`,
  `same motif`, `source`, `previous version`, or `in the style of the attached
  track`. Write the musical subject, texture, pacing, and arrangement directly
  as if no reference had been supplied.
- Use instrumental-only prompts. Explicitly include `no lyrics`, `no vocals`, `no voice`.
- If the user says not to use negative prompts, rely on Suno's Instrumental option and omit all negative wording from the prompt text.
- Do not use prompt terms that ask for looping, exact duration, or clip length. Avoid words and phrases like `loop`, `loopable`, `seamless loop`, `clean ending`, `90 seconds`, `two minutes`, `2:00`, `specific length`, or `duration`. These tend to produce very short Suno clips.
- Keep Suno-facing titles and prompts abstract and self-contained: use motion-study names and describe only musical subject, texture, pacing, and arrangement. Do not add a negative or avoidance clause about omitted product context.
- For Ring Shift, do not put `game`, `mobile`, `app`, `menu`, `mode`, `level`, `puzzle game`, `UI`, `button`, or similar product/interface context into Suno-facing titles or prompts. Use abstract stone-mechanism study titles and describe a self-contained instrumental composition.
- Describe the musical subject directly: a concentrated thinking piece for shifting blocks and rolling spheres, with deliberate motion, clean spatial gestures, recurring motifs, natural transitions, and a full arrangement.
- Prefer distinctive textures that fit tactile thought and motion: prepared piano, bowed vibraphone, glass harmonics, low clarinet, soft resonant metal, brushed paper, wooden knocks, restrained hand percussion, warm upright bass, and close-miked room tone.
- Separate relaxed variants from focused variants by tempo, density, register, silence, and percussion intensity.
- Keep any negative clauses about vocals only. Do not add broad "avoid" lists to Suno prompts unless the user specifically requests them.
- If the user rejects bright cue-like timbres and asks not to mention them, do not use negative timbre lists. Use positive instrumentation only: low strings, low winds, muted drums, felted bass-register piano, wood knocks, stone scrape, room tone, silence, and slow pulse.

For Ring Shift, start from this prompt family and vary density/register per track while preserving the same source motif:

`instrumental only, no vocals, no lyrics, no voice. low ritual mechanism study for concentric stone rings and slow hidden rotations, bowed double bass, low cello, bass clarinet, contrabassoon, felted prepared piano in the bass register, muted frame drum, hand drum skin, wood knocks, stone scrape, heavy air, long pauses, patient circular pulse, matte chamber tone, recurring low motif, natural transitions, full arrangement`

For Chroma Shift, start from this prompt family and adjust density per variant:

`instrumental only, no vocals, no lyrics, no voice. concentrated thinking piece for shifting blocks and rolling spheres, prepared piano pulses, bowed vibraphone glow, glass harmonics, low clarinet shadows, soft resonant metal, brushed paper texture, wooden knocks, warm upright bass, deliberate motion, clear spatial gestures, recurring motif, natural transitions, full arrangement`

### Duration Gate And Extension

Suno often generates clips that are too short when prompted with loop or length language. Treat 2:00 as the minimum acceptable duration for music assets.

- After every generation, check each candidate duration before accepting it into a manifest or app asset set.
- Reject any candidate shorter than 120 seconds, even if the musical idea is good.
- Do not regenerate from scratch just because a short candidate is promising. Use Suno's `Extend` workflow on that candidate first, then evaluate the extended result.
- Keep extending until the candidate is at least 120 seconds or the musical quality clearly degrades. If quality degrades, mark it rejected and start a new candidate with prompt-safe wording.
- Only download/package final accepted tracks after they pass the duration gate. If a workflow needs a quick placeholder, label it explicitly as a placeholder and do not treat it as final Suno music.
- When documenting candidates, record `duration_seconds`, `source_id`, `extended_from`, and whether the candidate passed the duration gate.

For Screwdriver 2026, keep these intended asset names unless the user changes the plan:

| File | Suno title direction |
| --- | --- |
| `music_menu.mp3` | `Screwdriver 2026 - Primary Assembly Study` |
| `music_tutorial.mp3` | `Screwdriver 2026 - Quiet Assembly Study` |
| `music_zen.mp3` | `Screwdriver 2026 - Low Density Assembly Study` |
| `music_easy.mp3` | `Screwdriver 2026 - Open Assembly Study` |
| `music_flat.mp3` | `Screwdriver 2026 - Flat Plate Study` |
| `music_cluster.mp3` | `Screwdriver 2026 - Clustered Plate Study` |
| `music_color_tutorial.mp3` | `Screwdriver 2026 - Quiet Color Study` |
| `music_color.mp3` | `Screwdriver 2026 - Dense Color Study` |
| `music_cascade_tutorial.mp3` | `Screwdriver 2026 - Quiet Cascade Study` |
| `music_cascade.mp3` | `Screwdriver 2026 - Dense Cascade Study` |

## Download Workflow

The Windows Firefox Store-app profile has the Suno login:

`/mnt/c/Users/dhaup/AppData/Local/Packages/Mozilla.Firefox_n80bbvh6b1yt2/LocalCache/Roaming/Mozilla/Firefox/Profiles/ibp6vus3.default-release`

Use a temporary copy of this profile, not the live profile, when driving with Playwright. Copy enough state for Suno:

```bash
src='/mnt/c/Users/dhaup/AppData/Local/Packages/Mozilla.Firefox_n80bbvh6b1yt2/LocalCache/Roaming/Mozilla/Firefox/Profiles/ibp6vus3.default-release'
dest='/tmp/suno-windows-firefox-profile'
rm -rf "$dest"
mkdir -p "$dest"
rsync -a --exclude='storage' --exclude='cache2' --exclude='startupCache' --exclude='shader-cache' --exclude='sessionstore-backups' --exclude='datareporting' --exclude='minidumps' --exclude='crashes' "$src/" "$dest/"
mkdir -p "$dest/storage/default"
rsync -a "$src/storage/default/https+++suno.com" "$dest/storage/default/"
rsync -a "$src/storage/default/https+++challenges.cloudflare.com^partitionKey=%28https%2Csuno.com%29" "$dest/storage/default/" 2>/dev/null || true
rsync -a "$src/storage/default/https+++hcaptcha-assets-prod.suno.com" "$dest/storage/default/" 2>/dev/null || true
```

Launch Playwright Firefox against that copied profile to verify login before the first download. The marker to check is usually `d_haupt82`; do not print cookies, localStorage, or tokens.

Suno player audio may expose `.m4a`, and the direct MP3 endpoint usually exists:

`https://cdn1.suno.ai/<song-id>.mp3`

This MP3 is lightweight, not the highest-quality asset. In a May 2026 check, Suno served the direct MP3 as 64 kbps, 48 kHz stereo. Pro/Premier UI downloads also expose `WAV Audio Pro`; that path produces 48 kHz, 16-bit stereo PCM WAV, around 1.536 Mbps. Use WAV as the source/master when quality matters, then encode down for app size if needed.

WAV download behavior:

- Get the song links/UUIDs from Chrome/OpenClaw, then open each link in Firefox/Playwright for downloads. Do not make Firefox scrape a library page for the batch unless Chrome link collection is unavailable.
- Use the logged-in Firefox UI clicks only: `More menu contents` -> `Download` -> hover/open `Download` -> `WAV Audio` -> wait for the popup -> click `Download File`.
- When clicked, Playwright should log a normal download event and a `cdn1.suno.ai/<song-id>.wav` response.
- Do not wait only for the `WAV Audio` click to emit a download; it first calls `convert_wav/`, then `wav_file/`, then shows the `Download File` button.
- Avoid brittle auth-header/API shortcuts. They may work in one session and fail in another. Use visible Firefox UI actions for WAV.
- When a page represents a cover/remix, verify the download target by observing the `convert_wav`, `wav_file`, or downloaded filename. If it references the source/base song instead of the intended UUID, go back to Chrome/OpenClaw, collect the clip's own card/list link, then in Firefox target that clip's own card/list or playbar menu. The top page menu may belong to the source track.
- Prefer robust visible anchors over hidden API state: in Firefox, confirm the playbar or card contains the Chrome-collected UUID/title before clicking its nearby `More menu contents` button.

Use `/mnt/c/Users/dhaup/Downloads` as the Windows Downloads path.

For lightweight MP3-only downloads, prefer the page-based helper. It opens the logged-in song page, waits for the embedded completed clip data, extracts the actual media URL, and then downloads. This avoids the race where `/song/<id>` is visible before `https://cdn1.suno.ai/<id>.mp3` is ready:

```bash
node /home/hod/.codex/skills/suno-music-workflow/scripts/suno_download_from_page.cjs \
  --output-dir /mnt/c/Users/dhaup/Downloads \
  music_menu_creepy=<song-id-or-url>
```

The older bundled helper can still use the public MP3 endpoint directly when you already know the CDN file is ready:

```bash
python3 /home/hod/.codex/skills/suno-music-workflow/scripts/download_suno_mp3.py \
  --output-dir /mnt/c/Users/dhaup/Downloads \
  music_cascade=6c4cc4bb-2dce-42db-bd11-43f92017d7bf
```

Arguments may be raw UUIDs, Suno `/song/<uuid>` URLs, or `filename=uuid` mappings. The helper writes MP3 files and does not require secrets. Do not use it when the user asked for highest quality or WAV masters.

For Android background music, encode from WAV masters at 96 kbps stereo MP3 as the default. Use 128 kbps only for tracks with audibly damaged transients or dense percussion after listening. Keep the WAVs outside the Android raw resources as source masters.

When batch converting with ffmpeg inside a shell loop, pass `-nostdin` or materialize the file list before the loop. Otherwise ffmpeg can consume bytes from the loop's stdin and corrupt every other input path.

## Known May 2026 Batch

If resuming the Screwdriver 2026 Suno batch from 2026-05-24, these IDs were captured. Treat them as candidates until the user selects final takes.

| Title | Candidate IDs |
| --- | --- |
| Primary Mechanical Study | `24f7a7e9-2a2a-433b-ae77-3f65aa91d678`, `7bcb2169-ad75-48c6-845e-ff0a27bdc5b2` |
| Primary Assembly Study | `2a65d358-3d62-4787-9137-6e7a52fbf7c4`, `8a61f21f-76b1-4008-b712-6c19b5b2ab92` |
| Quiet Assembly Study | `2df042a5-1351-4bf6-ad76-dbec0b249b22`, `e14fa0a8-ddcb-4a6c-aee6-775c42722857` |
| Low Density Assembly Study | `32142039-3734-45e7-bd5b-88241bf2bdd8`, `e18237f1-eb43-460a-94e6-c8ad1465f0b2` |
| Open Assembly Study | `f983a20f-6342-49a8-8cf4-3b4528547824`, `9aff140e-babf-4829-aa88-ad9c38191f33` |
| Flat Plate Study | `71a5ff4d-67d8-4080-ba45-69caa9fc21f9`, `eb7d5df2-ab9d-425b-94fd-fe9dab01924e` |
| Clustered Plate Study | `d1b7e0f4-b57c-46dc-a116-690d1440264b`, `b4122202-a1b9-467a-81bb-7ab2b9b326b6` |
| Quiet Color Study | `3e74d2d6-d212-4e38-a7e3-7f30352c5aaf`, `2a576219-0779-44a4-b719-235950a51190` |
| Dense Color Study | `3ea3e2ad-52e0-4f80-aee4-e6574ad4dc9b`, `7e0a412f-92dc-4a0f-b9f2-632086ef8f70` |
| Quiet Cascade Study | `3eb57b03-9bc3-4ce7-bb45-484945960fba`, `b37c114e-bab1-4b33-81b2-e76eb8705987` |
| Dense Cascade Study | `6c4cc4bb-2dce-42db-bd11-43f92017d7bf`, `6cd86038-96ab-4525-8830-e10629704b14` |

The verified test download was `6c4cc4bb-2dce-42db-bd11-43f92017d7bf` saved as `C:\Users\dhaup\Downloads\screwdriver_cascade_challenge_test.mp3`.

The app install from this batch ships both candidates for each app track. Runtime chooses between the base file and `_alt` variant for each mode track and avoids immediate repeats when switching back to a track.

| App file | Source ID |
| --- | --- |
| `music_menu.mp3` | `2a65d358-3d62-4787-9137-6e7a52fbf7c4` |
| `music_menu_alt.mp3` | `8a61f21f-76b1-4008-b712-6c19b5b2ab92` |
| `music_tutorial.mp3` | `2df042a5-1351-4bf6-ad76-dbec0b249b22` |
| `music_tutorial_alt.mp3` | `e14fa0a8-ddcb-4a6c-aee6-775c42722857` |
| `music_zen.mp3` | `32142039-3734-45e7-bd5b-88241bf2bdd8` |
| `music_zen_alt.mp3` | `e18237f1-eb43-460a-94e6-c8ad1465f0b2` |
| `music_easy.mp3` | `f983a20f-6342-49a8-8cf4-3b4528547824` |
| `music_easy_alt.mp3` | `9aff140e-babf-4829-aa88-ad9c38191f33` |
| `music_flat.mp3` | `71a5ff4d-67d8-4080-ba45-69caa9fc21f9` |
| `music_flat_alt.mp3` | `eb7d5df2-ab9d-425b-94fd-fe9dab01924e` |
| `music_cluster.mp3` | `d1b7e0f4-b57c-46dc-a116-690d1440264b` |
| `music_cluster_alt.mp3` | `b4122202-a1b9-467a-81bb-7ab2b9b326b6` |
| `music_color_tutorial.mp3` | `3e74d2d6-d212-4e38-a7e3-7f30352c5aaf` |
| `music_color_tutorial_alt.mp3` | `2a576219-0779-44a4-b719-235950a51190` |
| `music_color.mp3` | `3ea3e2ad-52e0-4f80-aee4-e6574ad4dc9b` |
| `music_color_alt.mp3` | `7e0a412f-92dc-4a0f-b9f2-632086ef8f70` |
| `music_cascade_tutorial.mp3` | `3eb57b03-9bc3-4ce7-bb45-484945960fba` |
| `music_cascade_tutorial_alt.mp3` | `b37c114e-bab1-4b33-81b2-e76eb8705987` |
| `music_cascade.mp3` | `6c4cc4bb-2dce-42db-bd11-43f92017d7bf` |
| `music_cascade_alt.mp3` | `6cd86038-96ab-4525-8830-e10629704b14` |
