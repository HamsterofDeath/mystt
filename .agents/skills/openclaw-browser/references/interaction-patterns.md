# Browser Interaction Patterns

Read this reference completely when controlling custom/lazy widgets, handling native JavaScript
dialogs, or monitoring long page-managed uploads.

## Custom widgets: synthetic click vs trusted click

Play Console and other Angular/Material-heavy apps mix controls that need different techniques.
A widget can appear to respond (`aria-expanded` changes) while never rendering its options.

- Use `eval` with `.click()` as a synthetic click for plain buttons, links, and simple checkbox
  hosts. It also works for reading or assigning ordinary input values.
- Use the controller's trusted `click <selector>` for custom dropdowns and comboboxes that render
  options lazily.
- Tag a difficult target with a stable ID using `eval`, then trusted-click that ID:

  ```bash
  node pinned-tab-ctl.js eval '(function(){var d=[...document.querySelectorAll("div[role=button]")].find(x=>/Kategorie auswählen/.test(x.textContent)&&x.offsetParent!==null);d.id="catTrigger";return "tagged";})()'
  node pinned-tab-ctl.js click "#catTrigger"
  node pinned-tab-ctl.js eval '(function(){[...document.querySelectorAll("[role=option]")].forEach(o=>{if(o.textContent.trim()==="Arcade")o.id="optArcade"});return "ok";})()'
  node pinned-tab-ctl.js click "#optArcade"
  ```

- Resolve required fields instead of retrying disabled buttons.
- Avoid `press Escape` when it can close the whole edit dialog and discard unsaved work. Click a
  specific option or cancel control instead.
- Write screenshots to a WSL-side path such as `/tmp/...`; a Windows path can hang.

## Native JavaScript confirm and prompt dialogs

An ordinary Playwright click auto-dismisses `confirm()` or `prompt()` when no dialog listener is
installed. The click command can report success even though the page action did not run.

Use guarded commands with an expected message substring:

```bash
node pinned-tab-ctl.js click-confirm '#publishButton' 'Set build 123 live'
node pinned-tab-ctl.js click-prompt '#newBranchButton' 'closed-beta' 'enter new app branch name'
```

These commands dismiss unexpected dialog types or messages instead of accepting them. Use
`click-prompt` only for non-secret values such as a branch name. Never pass passwords, 2FA codes,
recovery answers, or other secrets through command arguments. Let the user complete
authentication dialogs in the visible browser.

## Long page-managed uploads

Do not treat the upload-button click as completion. Do not navigate or close the pinned tab while
the page owns an active upload.

1. Identify the progress element and terminal result/status element before starting.
2. Poll those exact elements at bounded 20–45 second intervals. When jQuery is present,
   `jQuery.active` is a useful secondary count of queued or in-flight XHRs.
3. Treat an initially zero progress value as inconclusive. Chunked uploaders can prepare or queue
   many requests before completed bytes appear.
4. Confirm a terminal server result such as a manifest/build ID or explicit success message.
   Progress reaching 100% without a server result is insufficient.
5. If progress appears stuck, inspect completed resource timings or attach CDP Network monitoring
   to the same pinned target. Do not create a second control tab and do not call
   `browser.close()` on a remote CDP connection.
