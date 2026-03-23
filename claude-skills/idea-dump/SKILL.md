---
name: idea-dump
description: Use when you have a messy, stream-of-consciousness idea — takes raw, unstructured ideas and restructures them into a clean, actionable prompt, then auto-enters plan mode.
user_invocable: true
argument: The raw idea or messy prompt to restructure
---

# Idea Dump

You are receiving a raw, unstructured idea dump from the user. Your job is to transform it into a clear, structured prompt and then enter plan mode.

## Process

### Step 1: Parse
Read the user's raw input carefully. Identify:
- The core intent (what they actually want to accomplish)
- Any discrete tasks or deliverables mentioned
- Constraints (tech stack, patterns, things to avoid)
- Preferences (style, approach, priorities)
- Verification criteria (how to know it's done)

### Step 2: Restructure
Format the parsed input into this structure:

```
## Objective
One-sentence summary of what needs to happen.

## Scope
- **In scope:** what this covers
- **Out of scope:** what this does NOT cover

## Requirements
1. First deliverable
2. Second deliverable
3. ...

## Constraints
- Tech stack, patterns, or approaches to use
- Things to avoid or not change

## Verification
- How to confirm the work is done and correct
```

### Step 3: Present
Show the restructured prompt to the user. Say:

> Here's your idea, restructured:

Then display the formatted prompt.

### Step 4: Enter Plan Mode
After presenting the restructured prompt, immediately enter plan mode using `EnterPlanMode` to begin planning the implementation.

## Guidelines

- Be faithful to the user's intent — don't add scope they didn't ask for
- If something is ambiguous, make a reasonable assumption and note it in the output
- Collapse duplicates — if they said the same thing three ways, pick the clearest one
- Infer verification steps from the requirements if none were stated
- Keep it concise — the restructured prompt should be shorter and sharper than the input

## Examples

### Example 1: Feature Implementation

**Raw input:**
> ok so i want like a dark mode toggle on the settings page, it should save to localstorage and also maybe the navbar should react to it too, oh and make sure it doesn't flash white on reload

**Restructured:**

## Objective
Add a dark mode toggle to the settings page that persists across sessions and applies globally without flash.

## Scope
- **In scope:** Settings page toggle, localStorage persistence, navbar theming, flash prevention
- **Out of scope:** Per-component theme overrides, system preference detection

## Requirements
1. Add a dark mode toggle switch to the settings page
2. Persist the user's preference in localStorage
3. Apply the theme to the navbar and full page
4. Prevent white flash on page reload (apply theme before render)

## Constraints
- Use localStorage (not cookies or server-side)
- Must work with existing CSS architecture

## Verification
- Toggle switches between light and dark mode
- Preference survives page refresh
- No white flash on reload when dark mode is active

---

### Example 2: Multi-Task Orchestration

**Raw input:**
> need to refactor the auth module, also the tests are broken for the user service, and while you're at it can you update the README with the new env vars we added last week, the ones for stripe and sendgrid

**Restructured:**

## Objective
Refactor the auth module, fix user service tests, and update README with new environment variables.

## Scope
- **In scope:** Auth module refactor, user service test fixes, README env var docs
- **Out of scope:** New features, other test suites, non-auth refactoring

## Requirements
1. Refactor the auth module for clarity/maintainability
2. Fix broken tests in the user service test suite
3. Document Stripe and SendGrid environment variables in README

## Constraints
- Do not change auth module's public API (unless necessary for fixes)
- Preserve existing test coverage

## Verification
- Auth module is cleaner with no behavior changes
- All user service tests pass (`python -m pytest`)
- README includes Stripe and SendGrid env var documentation

---

### Example 3: Pipeline / Script Execution

**Raw input:**
> i have a csv with like 50k user records that need to be backfilled into the new profiles table, the csv has email, name, and signup_date columns, run it in batches so we don't kill the db, and log progress somewhere

**Restructured:**

## Objective
Create and run a backfill script to migrate 50k user records from CSV into the profiles table.

## Scope
- **In scope:** CSV parsing, batch inserts, progress logging
- **Out of scope:** Data validation beyond schema, rollback strategy, deduplication

## Requirements
1. Parse CSV with columns: email, name, signup_date
2. Insert records into the profiles table in batches
3. Log progress to a file (count processed, errors, completion)
4. Run with nohup/background so progress isn't lost

## Constraints
- Use batch inserts (not row-by-row) to protect DB performance
- Stream output to a log file

## Verification
- All 50k records appear in the profiles table
- Log file shows completion with error count
- No DB timeouts or connection issues during run

---

### Example 4: Bug Investigation

**Raw input:**
> users are reporting that sometimes when they submit the checkout form it just spins forever, no error, nothing in the console, it works fine for me locally but prod is broken, maybe a timeout thing? idk

**Restructured:**

## Objective
Investigate and fix the checkout form submission hanging in production.

## Scope
- **In scope:** Checkout form submission flow, API endpoint, timeout handling, prod-specific config
- **Out of scope:** Other forms, general performance optimization

## Requirements
1. Trace the checkout submission flow from frontend to backend
2. Identify why requests hang without error in production
3. Check for timeout misconfigurations, missing error handlers, or environment differences
4. Implement a fix with appropriate error handling and user feedback

## Constraints
- Reproduce or confirm the issue before fixing
- Don't change unrelated checkout logic

## Verification
- Checkout form submission completes or shows a clear error within a reasonable timeout
- Test the fix against production-like conditions
- No regression in the normal checkout flow

---

### Example 5: UI/UX Change

**Raw input:**
> the dashboard looks cluttered, can we move the stats cards to a grid layout, 2 columns on desktop 1 on mobile, and maybe add some breathing room between sections, also the chart is too wide it bleeds off screen on smaller laptops

**Restructured:**

## Objective
Clean up the dashboard layout with responsive grid, better spacing, and contained chart width.

## Scope
- **In scope:** Stats card layout, section spacing, chart width constraint, responsive breakpoints
- **Out of scope:** Dashboard data/logic changes, new components, color/theme changes

## Requirements
1. Arrange stats cards in a 2-column grid (desktop) / 1-column (mobile)
2. Add consistent spacing between dashboard sections
3. Constrain chart width so it doesn't overflow on smaller screens
4. Ensure layout works across common breakpoints

## Constraints
- Use existing CSS framework/patterns
- Don't change component logic or data

## Verification
- Desktop shows 2-column stats grid with breathing room
- Mobile shows single-column layout
- Chart stays within viewport on ~1366px wide screens
- No horizontal scrollbar at any breakpoint

## Gotchas

_No known gotchas yet. Add lessons here as they emerge from real usage._
