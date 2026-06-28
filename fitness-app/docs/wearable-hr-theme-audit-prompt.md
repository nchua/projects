# Next-session prompt — Wearable-HR theme conformance audit

> Paste the block below into a fresh Claude Code session in `fitness-app/`.
> It runs a full theme-conformance pass over everything we added for wearable-HR
> (Chunk D HR display + Chunk C settings), against the approved ARISE design system.

---

Do a **full theme-conformance audit** of all the wearable-HR UI additions in the fitness-app iOS app. Goal: make sure every new surface follows the ARISE design system exactly — **color, fonts, buttons, highlights/glows, dividers, badges, spacing, nil-state degradation** — and that the **quest-type strings still line up backend↔iOS**. This is a polish/QA pass: find deviations, then fix them.

**Load the theme source-of-truth first (read before judging any code):**
- `ios/FitnessApp/Utils/Colors.swift` + `Utils/Fonts.swift` — the tokens.
- `docs/mockups/wearable-hr-ui-mockup.html` — the **approved visual target**; it has an embedded color-palette map (every token as a labeled swatch) and the 4 HR render states. Treat it as the reference for how the new surfaces should look.
- Recalled memory `reference-arise-design-palette` — palette + conventions + the **two lift-color systems** gotcha (`exerciseColor(for:)` vs `PowerLevelsCard.BigThreeLift.liftColor`).
- `docs/wearable-hr-v1-build-spec.md` (Chunk D + E) — what was built.
- `backend/app/models/quest.py` (the `QuestType` enum) + `backend/app/services/quest_service.py` (seed quest definitions + the `progress`/`target_value` logic) — the **canonical `quest_type` strings + units** the iOS quest switches must mirror. ⚠️ A rename `training_time → workout_duration` landed after our work (commit `051eaac`), and the backend quest files changed — so this is now a live contract to re-verify, not assume.

**Scope — audit every addition + edit:**
- `ios/FitnessApp/Components/AriseHRZoneBar.swift`
- `ios/FitnessApp/Components/AriseSourceBadge.swift`
- `ios/FitnessApp/Components/AriseWorkoutHRSection.swift`
- `ios/FitnessApp/Views/Home/HomeView.swift` — the Biometrics section in `WorkoutSheetHeader`
- `ios/FitnessApp/Views/History/HistoryView.swift` — source badge, Heart-Rate detail block, per-set HR column
- `ios/FitnessApp/Components/DailyQuestsCard.swift` + `QuestDetailSheet.swift` — HR quest icons + copy
- Chunk C surfaces (if touched): `Views/Profile/ProfileView.swift` settings rows + `Views/Profile/AppleHealthWorkoutSettingsView.swift`

**Checklist — report each item PASS or a deviation (with `file:line` + the token/rule it violates):**
1. **Color** — every color resolves to a `Colors.swift` token (flag any raw hex), used for its intended role; HR-zone palette matches the locked z1..z5; strain = `.orange`; provenance-badge colors correct; no off-palette greens/oranges (watch the two greens `#33FF88` vs `#00FF88`, and the two lift-color systems).
2. **Fonts** — display/values = Orbitron (`ariseDisplay`); headers/titles/dates = Rajdhani (`ariseHeader`); labels/metrics/tags = JetBrains Mono (`ariseMono`); body = Inter/`.system`. Flag a header font on body text or vice-versa.
3. **Highlights / glow** — value glows are subtle (`color.opacity(0.4)`, radius ~10) and only where the app uses them; StatCard icons stay gray (`textSecondary`); no over-glow.
4. **Buttons / interactive** — tap targets, pressed/disabled states, the disabled "Connect WHOOP — coming soon" row at `.opacity(0.5)` non-interactive, any claim/accept button matches existing styles.
5. **Dividers / borders / cards** — `AriseDivider` (gradient) where the app divides; card chrome = `voidMedium` fill + `ariseBorder` (cyan@0.2) stroke, cornerRadius 4 (quests use 12).
6. **Badges / pills** — `AriseSourceBadge` chrome matches the prior inline badge; quest icons are emoji (DailyQuestsCard), XP is `textMuted`, no fabricated progress bar in the list.
7. **Nil-safety / degradation** — a workout with all HR nil renders byte-identically to before (no phantom section, badge, divider, or HR column).
8. **Consistency vs the mockup** — each new surface visually matches `wearable-hr-ui-mockup.html`.
9. **Quest-type contract (backend ↔ iOS)** — every `quest.questType` string literal in the iOS switches (`DailyQuestsCard.questIcon` and `QuestDetailSheet.questEmoji` / `progressText` / `motivationalText`) must EXACTLY match a canonical `quest_type` the backend emits. Diff against the backend source of truth (`quest.py` `QuestType` enum + `quest_service.py` seeds), **not** the spec prose. Flag: (a) any **stale string** — e.g. `training_time` left behind after the `workout_duration` rename; (b) any backend `quest_type` with **no iOS case** (silently falls through to the default ⚔️/💪 icon + generic `X / Y` copy — easy to miss); (c) any **unit mismatch** — confirm `hr_zone_time` = minutes, `peak_hr` = bpm, `session_strain` = strain still match what the backend writes to `progress`/`target_value` (and that `workout_duration`'s unit/copy is right). Report each as `file:line` + fix.

**Method:** read the theme refs → diff each file against the tokens/conventions → produce a conformance report (deviations first, each with `file:line` + proposed fix) → apply the safe fixes → run the iOS build gate (`cd ios && xcodegen generate`; `xcodebuild -project FitnessApp.xcodeproj -scheme FitnessApp -destination 'generic/platform=iOS Simulator' build 2>&1 | grep "error:"` empty; `bash scripts/lint-entitlements.sh`) → commit on `main` (or a branch). Note: SourceKit "cannot find in scope" warnings are cross-file false positives — `xcodebuild` is authoritative.
