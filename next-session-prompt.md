Drive PR #31 in nchua/projects (https://github.com/nchua/projects/pull/31, branch `claude/fitness-hunt-submit-crash-l6tvgs`) to green and up to date with `main`. Then hand it back to me for an on-device check and the merge.

## Background
PR #31 fixes an iOS crash on every hunt submit. The Log screen bound rows by array index, and resetting the hunt emptied the array under mounted rows. The PR switches to id-based bindings via `Binding.element(matching:)`. It also adds Linux-only lint checks (`fitness-app/ios/scripts/lint-swiftui-bindings.sh`, plus `lint-fullscreen-cover.sh` wired into CI) and fixes `lint-entitlements.sh`. That script used the macOS-only PlistBuddy on an Ubuntu runner, so `main` CI has been red since Sept 6; `main` stays red until this PR merges. Read the PR description for details.

## Current state (head `92a9381`)
- Passed: "iOS — xcodebuild" (the Swift compiles), "iOS — lint", Alembic, gitleaks.
- Failed: "Backend — lint + tests", on one test this PR doesn't touch: `fitness-app/backend/tests/test_admin_users.py::TestListUsers::test_search_escapes_like_wildcards` (around line 313).
  - Root cause (verified): the backend pins `httpx==0.26.0`, which passes `%XX` through unencoded in query params. The test's tag is random hex, so `q=f"%{tag}"` is read as a percent-escape. When the tag starts with `3` followed by a digit (about 4% of runs), `%35…` decodes server-side to `5…`, a plain substring of both test users' emails, so both match and `assert ids == []` fails.
  - The server's LIKE escaping (`_escape_like` in `app/services/admin_read_service.py`) is correct; only the test is wrong.
  - Fix: search `f"%-{tag}"` instead. httpx 0.26 sends `%-` literally, and an unescaped wildcard would still match `pct-{tag}` and `plain-{tag}`, so the test still proves the escape. Add a one-line comment saying why.
- The branch is behind `main`; GitHub reports no conflict.

## Do
1. Subscribe to PR #31 activity.
2. Merge `origin/main` into the branch with a merge commit, not a rebase.
3. Fix the flaky test.
   - Prove the fix first: temporarily force a tag starting with `35` (e.g. monkeypatch `uuid.uuid4`) and show the old query fails and the new one passes.
   - Then run the whole backend suite:
     `cd fitness-app/backend && python3 -m venv venv && venv/bin/pip install -r requirements.txt -r requirements-dev.txt && SECRET_KEY=test JWT_SECRET_KEY=test venv/bin/python -m pytest tests/ -n auto -q`
   - The test isn't this PR's, so put the fix in its own small PR against `main` and port the same change into PR #31.
4. Run `bash fitness-app/ios/scripts/lint-entitlements.sh`, `lint-swiftui-bindings.sh` and `lint-fullscreen-cover.sh`. Then push and follow CI until every job on PR #31's head is green.
5. The branch carries the last session's handoff files, `session-state.md` and `next-session-prompt.md`, at the repo root. Read `session-state.md` first. Delete both in your final push so they don't land on `main`.

## Constraints
- No simulator or UI tests in CI; I don't want extra macOS minutes. Keep the test suite lean.
- The cloud container has no Xcode. Don't change Swift unless CI's iOS job requires it; that job is the compile check.
- Don't merge. When CI is green, tell me, and remind me of the on-device check: rebuild in Xcode, finish a hunt with one single exercise and one superset, tap through PR/XP → Continue, and confirm it lands on the idle screen.
- Open question for me, not you: should the repo have a PR template? The last session recommended skipping it (PRs are rare and mostly Claude-authored; the checks live in CI and `CLAUDE.md`).
