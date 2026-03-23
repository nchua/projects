---
name: council
description: Use when a task needs multiple perspectives or expertise areas — transforms raw idea dumps into a dynamic council of specialized agents that collaborate to plan and execute the work.
user_invocable: true
argument: The raw idea or messy prompt to restructure and execute with a council of agents
---

# Council

You are receiving a raw, unstructured idea dump from the user. Your job is to transform it into a clear objective, assemble the right team of agents, get user approval on the team, have them collaboratively plan, and then execute.

## Process Overview

```
Raw Idea → Parse → Determine Council → Present Team → Approve → Agents Work → Synthesize Plan + Strategy → Approve → Execute
```

## Step 1: Parse the Idea

Read the user's raw input carefully. Identify:
- The core intent (what they actually want to accomplish)
- The category of work (feature, bug fix, refactor, infrastructure, design overhaul, data migration, etc.)
- The complexity level (single-domain vs. cross-cutting)
- Any discrete tasks or deliverables mentioned
- Constraints and preferences

Restructure it into a concise objective statement:

```
## Objective
One-sentence summary of what needs to happen.

## Scope
- **In scope:** what this covers
- **Out of scope:** what this does NOT cover

## Key Requirements
Bulleted list of what must be delivered.
```

## Step 2: Determine the Council

Based on the parsed idea, decide which agents are needed. You are the **Orchestrator** — your job is to pick the right team size and composition for the task.

### Guiding Principles

- **Minimum viable team.** Don't spin up agents that won't contribute meaningfully. A bug fix needs an engineer, not a committee.
- **Match agents to the work.** If there's no UI change, don't add a designer. If there's no cross-team coordination needed, don't add a PM.
- **Scale with complexity.** Simple tasks get 1 agent. Medium tasks get 2-3. Large cross-cutting features might get 3-4.

### Agent Roster

Pick from these roles (or define a custom one if the task demands it):

| Role | When to Use | Responsibilities |
|------|-------------|------------------|
| **Senior Staff Engineer** | Always, for any code changes | Explores codebase architecture, identifies files to modify, determines technical approach, writes implementation plan, considers edge cases and backwards compatibility |
| **Product Designer** | UI/UX changes, new screens, layout overhauls | Reviews current UI, creates HTML mockup files for proposed changes, considers responsive behavior, accessibility, and interaction patterns |
| **Product Manager** | Cross-cutting features touching multiple systems, features needing prioritization or phasing | Defines acceptance criteria, determines execution order, identifies dependencies between workstreams, decides what ships in v1 vs. later |
| **QA Engineer** | Complex features with many edge cases, changes to critical paths | Defines test plan, identifies edge cases, writes verification criteria, considers regression risks |
| **Data Engineer** | Migrations, schema changes, backfills, analytics | Plans data model changes, migration strategy, rollback approach, data validation |
| **DevOps/Infra Engineer** | Deployment changes, CI/CD, environment config | Plans infrastructure changes, environment variables, deployment strategy |

### Collaboration Mode

You also decide the collaboration mode:

- **Hub-and-spoke** (default): Each agent works independently and reports to you. You synthesize their outputs. Use this when agent work is independent and doesn't need cross-validation.
- **Cross-review**: Agents review each other's outputs (e.g., engineer reviews designer's mockup for feasibility, PM reviews engineer's plan for completeness). Use this for complex features where alignment between roles matters.

## Step 3: Present the Team

Before spinning up any agents, present the proposed team to the user:

```
## Proposed Council

**Collaboration mode:** [Hub-and-spoke / Cross-review]

| Agent | Role | Task |
|-------|------|------|
| 1 | Senior Staff Engineer | [What they'll investigate/plan] |
| 2 | Product Designer | [What they'll design/mockup] |
| ... | ... | ... |

**Why this team:** [1-2 sentences explaining why you chose this composition]
```

Then ask the user to approve using `AskUserQuestion`:
- "Approve this council" (proceed)
- "Modify the team" (let them adjust)

**Do NOT spin up agents until the user approves.**

## Step 4: Run the Council

Once approved, spin up agents using the `Task` tool. Run independent agents **in parallel** for efficiency.

### Agent Prompt Template

Each agent receives a prompt structured like this:

```
You are a [ROLE] on a product council. Your job is to [RESPONSIBILITY].

## Context
[The parsed objective and scope from Step 1]

## Your Assignment
[Specific task for this agent]

## Output Format
[What they should return — see role-specific formats below]

## Guidelines
- Be thorough but concise
- Ground your analysis in the actual codebase (read real files, don't guess)
- Flag risks, open questions, or things you'd want to discuss with the team
- Do NOT write code or make changes — research and plan only
```

### Role-Specific Output Formats

**Senior Staff Engineer** should return:
```
## Technical Analysis
- Current architecture relevant to this change
- Files that need to be modified (with paths)
- Dependencies and potential conflicts

## Implementation Plan
1. Step-by-step changes with file paths
2. ...

## Risks & Open Questions
- Edge cases, backwards compatibility concerns, etc.
```

**Product Designer** should return:
```
## Current State
- Description of existing UI/UX

## Proposed Design
- Description of changes
- [Create HTML mockup files in the scratchpad directory if UI changes are significant]

## Interaction Details
- User flows, responsive behavior, animations, edge states
```

**Product Manager** should return:
```
## Acceptance Criteria
- Bulleted list of "done" conditions

## Execution Plan
- Recommended phasing/ordering
- Dependencies between workstreams

## Scope Decisions
- What's in v1, what's deferred
```

**QA Engineer** should return:
```
## Test Plan
- Key scenarios to verify
- Edge cases to cover

## Regression Risks
- What existing functionality could break
- Recommended regression tests
```

## Step 5: Synthesize

After all agents complete, synthesize their outputs into a unified plan:

```
## Council Summary

### Objective
[From Step 1]

### Design
[Designer's proposed changes, with links to mockups if created]

### Technical Plan
[Engineer's implementation steps]

### Acceptance Criteria
[PM's criteria]

### Test Plan
[QA's verification steps, if applicable]

### Execution Order
1. [First thing to do]
2. [Second thing to do]
3. ...

### Execution Strategy

**Recommended:** [Agent Team / Single Agent / Subagent Group]

**Rationale:** [Why this strategy fits the work]

**Plan:**
- [If Agent Team]: Which agents execute which portions, what runs in parallel
- [If Single Agent]: Which agent, sequential order of work
- [If Subagent Group]: List of discrete subtasks to delegate

### Risks & Open Questions
[Combined from all agents]
```

If using **cross-review** mode, after synthesizing, spin up a second round where agents review relevant parts of each other's work. Append any feedback to the plan.

### Execution Strategy Decision Guide

Use this table to choose the right execution strategy for the synthesized plan:

| Strategy | When to Use |
|----------|-------------|
| **Agent Team** | Independent parallel workstreams, each agent owns separate files |
| **Single Agent** | Tightly coupled work, overlapping files, benefits from full context |
| **Subagent Group** | Many (5+) independent, similarly-shaped tasks that can parallelize |

**Decision rules:**
1. 1 workstream or overlapping files → **Single Agent**
2. 2-4 distinct workstreams with separate file sets → **Agent Team**
3. 5+ similar independent tasks → **Subagent Group**
4. When in doubt → **Single Agent** (avoids coordination overhead)

## Step 6: Approve and Execute

Present the synthesized plan (including the Execution Strategy section) to the user. Enter plan mode using `EnterPlanMode` so the user can approve the plan and strategy before execution begins.

Once approved and you exit plan mode, execute according to the approved strategy:

### If Agent Team

Spin up council agents **in parallel** using the `Task` tool. Each agent receives:
- The full approved plan for context
- Their specific workstream and deliverables
- Their file boundaries (which files they own — no overlap between agents)

Use `TaskCreate` to create one task per agent's workstream. Track completion and resolve cross-agent dependencies in order.

### If Single Agent

Spin up **one agent** (typically the Senior Staff Engineer) to execute the full plan sequentially, step by step. The agent receives:
- The full approved plan
- Instructions to work through the execution order one step at a time

Use `TaskCreate` to create one task per step in the execution order. The agent marks each task complete as it progresses.

### If Subagent Group

Break the work into **discrete, fully independent subtasks**. Each subtask must:
- Touch a separate set of files (no overlap)
- Be completable without knowledge of other subtasks' results
- Have a clear, self-contained deliverable

Spin up a focused subagent per subtask **in parallel** using the `Task` tool. After all subagents complete, run a **final consistency check** — a single agent reviews all changes together to verify they integrate correctly and fix any conflicts.

## Examples

### Example 1: New Product Feature (3-agent council)

**Raw input:**
> i want to add a weekly summary screen to the app that shows your workout stats for the week, like total volume, workouts completed, maybe a chart, and it should be accessible from the home screen

**Parsed objective:** Add a weekly workout summary screen with stats and chart, accessible from the home screen.

**Council:**
| Agent | Role | Task |
|-------|------|------|
| 1 | Senior Staff Engineer | Investigate current home screen architecture, data APIs available, chart libraries in use, and plan the implementation |
| 2 | Product Designer | Review current app screens and design the weekly summary layout with mockups |
| 3 | Product Manager | Define what stats matter most, acceptance criteria, and whether this is one release or phased |

**Collaboration mode:** Cross-review (designer's mockup should be reviewed by engineer for feasibility)

---

### Example 2: Bug Fix (1-agent council)

**Raw input:**
> the screenshot processing is broken, it's returning empty exercise names sometimes

**Parsed objective:** Fix screenshot processing returning empty exercise names.

**Council:**
| Agent | Role | Task |
|-------|------|------|
| 1 | Senior Staff Engineer | Investigate the screenshot processing pipeline, identify where exercise names are lost, and fix |

**Collaboration mode:** N/A (single agent)

**Why:** This is a targeted bug in a single system. No design or coordination needed.

---

### Example 3: Data Migration (2-agent council)

**Raw input:**
> we need to migrate the workout data schema to support supersets, right now exercises are flat in a workout but we need to group them

**Parsed objective:** Restructure workout data model to support exercise groupings (supersets).

**Council:**
| Agent | Role | Task |
|-------|------|------|
| 1 | Senior Staff Engineer | Analyze current data model, design new schema with superset support, plan migration |
| 2 | Data Engineer | Plan the data migration strategy, write migration scripts, define rollback approach |

**Collaboration mode:** Cross-review (engineer and data engineer need to align on schema)

---

### Example 4: Major Feature Overhaul (4-agent council)

**Raw input:**
> i want to completely redo the coaching system, right now it's just goals but i want it to feel like a real AI coach that gives you personalized workout plans, tracks your progress against the plan, and adjusts based on how you're doing

**Parsed objective:** Rebuild the coaching system into a personalized AI coach with workout planning, progress tracking, and adaptive adjustments.

**Council:**
| Agent | Role | Task |
|-------|------|------|
| 1 | Senior Staff Engineer | Analyze current coaching architecture, plan backend changes for AI coaching, identify API and model changes |
| 2 | Product Designer | Design the coaching UX flow — plan view, progress tracking, coach interaction patterns |
| 3 | Product Manager | Define the MVP scope, phase the rollout, set acceptance criteria for v1 |
| 4 | QA Engineer | Identify edge cases in personalization, plan testing strategy for adaptive behavior |

**Collaboration mode:** Cross-review (this is a major feature — all agents should review for alignment)

## Guidelines

- **Be faithful to the user's intent** — don't add scope or agents they don't need
- **Err on fewer agents** — a lean team that moves fast beats a bloated committee
- **All agents must read real code** — no hallucinating file paths or architecture. Agents should use Glob, Grep, and Read tools to ground their analysis.
- **Mockups go in scratchpad** — designer mockups are written to the scratchpad directory, not the project
- **Flag disagreements** — if agents produce conflicting recommendations during cross-review, surface the conflict to the user rather than silently picking a side

## Gotchas

_No known gotchas yet. Add lessons here as they emerge from real usage._
