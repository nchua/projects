---
title: ""
status: draft # draft | reviewed | in-progress | built
created: YYYY-MM-DD
owner: Nick
target_repo: "" # path in this monorepo, or owner/name for another repo
---

# Title

_Copy this file to `YYYY-MM-DD-short-kebab-name.md`. Italic lines are instructions to the author — remove them in the finished spec. The finished spec is the only context fable (review) and Opus (implementation) receive. State every decision, constraint, path, and acceptance check here._

## Summary

_Two to four sentences: what will be built, who it is for, and what is true when it ships._

## Goal

_The outcome Nick wants, in concrete terms._

**Success criteria:**

- [ ] _Observable result that means the goal is met._

## Background and user problem

_Who has the problem, what they do today, and why this is worth building. Include the current-system facts an implementer needs, with file paths and behavior._

**Assumptions:**

- _Facts the implementer should treat as given._

## Scope

**In scope:**

- _Behavior this spec delivers._

**Non-goals:**

- _Nearby work this spec leaves undone, so the implementer does not build it._

## User stories and flows

_Add a story for each actor. Then write each primary flow as ordered steps, including the failure path that matters._

- As _someone_, I want _capability_, so that _outcome_.

### Flow: _name_

1. _Step._
2. _Step._
3. _What the user sees when it fails._

## Functional requirements

_Number every requirement. Each one is a single testable behavior. Refer to these IDs from milestones and tests._

- **FR-1.** _The system does X when Y._
- **FR-2.** _The system does X when Y._

## Technical design

_Choose the design. Name real modules, types, and endpoints in the target repo. Where several options would work, state the choice and the reason in one or two sentences._

### Architecture

_How the pieces fit together and where this change sits in the existing system._

### Data model

_Entities, fields, types, and relationships to add or change. Note migrations and compatibility with existing data._

### APIs and interfaces

_Endpoints, commands, function signatures, inputs, outputs, and errors. Include auth if the interface has any._

### Key components

_The modules or views to add or change, and the responsibility of each._

### Files to create or change

| Path | Change |
| --- | --- |
| `_path/to/file_` | _What changes and why._ |

### Constraints

_Patterns to follow, compatibility, performance, privacy, and security. Name environment variables for secrets; never write secret values._

### Edge cases and failure behavior

_Inputs and states that must behave a specific way, and what the user or caller sees when something fails._

## Tech stack and dependencies

_Languages, frameworks, and libraries. Prefer what the target repo already uses. List anything new, why it is needed, and any version constraint. Note services, config, and environment variables the work depends on._

## Implementation plan

_Order milestones so each one leaves the project in a working state. Later milestones may depend on earlier ones. Point acceptance criteria at requirement IDs._

### Milestone 1 — _name_

**Goal:** _What is true when this milestone is done._

**Steps:**

1. _Step._
2. _Step._

**Acceptance criteria:**

- [ ] _Check that closes this milestone (FR-1)._

_Append Milestone 2, 3, and so on in build order._

## Testing plan

_Name the commands to run and the cases that prove the requirements. Include manual checks a later agent can follow._

- **Automated:** _Command, and what it covers._
- **Cases:** _FR-1 — input, expected result._
- **Manual:** _Steps to perform, and what to look for._

## Risks

- **_Risk._** _What goes wrong and how likely it is._ **Mitigation:** _What to do._

## Open questions

_A spec moves to `reviewed` only after each question is answered here or given a default the implementer must follow._

- **Q1.** _Question, and why it blocks a decision._ **Default:** _What to do if nobody answers._

## Reviewer checklist

_For the fable review. Check each item against this file. Record findings in Review notes, then set `status` to `reviewed`._

- [ ] The spec can be reviewed and implemented from this file alone.
- [ ] The summary, goal, and success criteria are concrete.
- [ ] Scope and non-goals are explicit.
- [ ] User stories and flows cover the success path and the failure that matters.
- [ ] Requirements are numbered and testable.
- [ ] The design names architecture, data model, APIs, components, and files.
- [ ] Constraints, edge cases, and failure behavior are specified.
- [ ] Stack and dependencies match the target repo, and anything new is justified.
- [ ] Milestones are ordered, and each has acceptance criteria.
- [ ] The testing plan covers the requirements.
- [ ] Risks are identified, and every open question is resolved or has a default.
- [ ] `target_repo` is correct, and no secret values appear in the spec.

### Review notes

_Leave blank. The reviewer writes what was checked, what changed in the spec, and any defaults set for open questions._

## Status log

| Date | Status | Note |
| --- | --- | --- |
| YYYY-MM-DD | draft | Spec created. |
