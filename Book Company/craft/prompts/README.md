# Prompts

Versioned prompt files (SPEC §3.1). Loaded only via `bookgen.prompts.load_prompt`.

Format: front matter (`name`, `version`), then the role instructions, then a line
`=== user ===`, then the per-call template with `$placeholders` the stage fills.
The Craft Guide (and, after S3, the bible) are sent *before* these instructions as
cached system blocks (§8.4), so prompts can refer to "the Craft Guide" and "the bible".

Bump `version` when you change what a prompt asks for, and run `book eval` (§6.7)
before keeping the change. Every model call logs the prompt name, version and sha.
