# v2 Bug Bash — W6.J4

Running list of issues from week-5 personal usage. Triage at W6 Saturday into
P0 (data loss / demo blockers), P1 (visible regressions / broken flows),
P2 (papercuts), P3 (nice-to-have).

**State:** v2 was just shipped today (2026-04-26, commit `abdae61`). The
week-5 personal-usage window doesn't yet exist — there is nothing to triage.
This file is the running collection going forward.

## Triage rules

- P0 / P1 are fixed within W6.
- P2 / P3 are punted to `mockups/v2-1-backlog.md`.
- No issue is silently closed without a fix or a punt note.

## Issues observed (running list)

_(empty — populate during the week-5 personal-usage window)_

| # | Surface | Severity | Description | Status | Repro |
|---|---|---|---|---|---|
| — | — | — | — | — | — |

## Demo dry-run

After the bash, full ride must complete without stumbling:
read → finish → save → atlas → click → write → publish.

- [ ] Sign in (Google or magic link)
- [ ] Paste an article into `/read` and finish it
- [ ] Open `/library` List → see the new card with `· JUST SAVED ·` pulse
- [ ] Switch to Atlas tab → click a tag → re-center
- [ ] Open source side panel → REPLAY back into `/read`
- [ ] Open `/write` → create a new piece → autosave fires
- [ ] Toggle to NEWSLETTER → publish → slug minted
- [ ] Open atlas concept panel → confirm the new piece appears in the
      "Writings" section
