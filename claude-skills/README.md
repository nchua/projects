# Claude Skills

General-purpose Claude Code skills. Each skill lives in its own directory as a `SKILL.md` file.

## Installation

Copy any skill folder to `~/.claude/skills/`:

```bash
cp -r council ~/.claude/skills/
cp -r idea-dump ~/.claude/skills/
```

Then restart Claude Code. Invoke with `/council` or `/idea-dump`.

## Skills

### `/council`
Transforms a raw idea dump into a dynamic council of specialized agents (engineer, designer, PM, QA) that collaborate to plan and execute the work. Supports hub-and-spoke and cross-review collaboration modes.

### `/idea-dump`
Takes a messy, stream-of-consciousness idea and restructures it into a clean, actionable prompt with objective, scope, requirements, constraints, and verification criteria. Auto-enters plan mode after restructuring.
