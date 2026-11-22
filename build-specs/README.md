# Build specs

This folder holds one self-contained implementation spec per idea Nick wants built.

A spec is the handoff. A Cursor agent writes it from Nick's description. Later, in a separate session, Claude reviews it with fable and implements it with Opus. That later session has this file as its only context, so the spec carries every decision, constraint, file path, data shape, and acceptance criterion.

This folder is separate from `plans/`, which holds council summaries. New implementation handoffs go here. Specs stay in this folder even when the code they describe lives in a subdirectory of this monorepo or in another repository.

## Workflow

1. **Describe.** Nick describes an idea.
2. **Specify.** A Cursor agent turns that description into the most complete implementation plan it can, saved as one markdown file in this folder. Copy `TEMPLATE.md`. Do not edit the template.
3. **Review.** Claude reviews the spec with fable, using only the file. The reviewer works through the checklist, resolves or sets a default for every open question, and sets `status` to `reviewed` when the spec is ready to build as written.
4. **Build.** Claude implements the spec with Opus. Set `status` to `in-progress` when implementation starts and to `built` when the work has landed. Implementation starts from a `reviewed` spec.

When a spec is added or its status changes, update the index below.

## Naming

`YYYY-MM-DD-short-kebab-name.md`

- The date is the day the spec is created.
- The slug is a few kebab-case words naming the idea.
- Example: `2026-11-22-workout-export-filters.md`.
- One idea per file. If the idea changes into a different piece of work, write a new spec.

## Status

Each spec tracks its lifecycle in YAML front matter. Move forward in this order. If review finds gaps, set the spec back to `draft`, update it, and review again.

| Status | Meaning | Set by |
| --- | --- | --- |
| `draft` | Written and waiting for review. Open questions may still be open. | The Cursor agent that wrote the spec |
| `reviewed` | Fable review is done. Every open question is answered or has a default. Safe to build as written. | Claude, after the fable review |
| `in-progress` | Implementation is underway. | Claude, when Opus starts |
| `built` | The work has landed. | Claude, when Opus finishes |

## Index

| Spec | Title | Status | Created | Owner | Target repo |
| --- | --- | --- | --- | --- | --- |
| [2026-11-21-field-notes-learning-module.md](2026-11-21-field-notes-learning-module.md) | Field Notes learning module | draft | 2026-11-21 | Nick | nchua/field-notes |
