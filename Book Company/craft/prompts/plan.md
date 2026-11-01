---
name: plan
version: 1
---
You are planning one episode of the series described in the bible above, as a twelve-spread picture-book plan. A writer will turn your plan into text and an illustrator will draw each spread, so every beat must be a picturable moment that happens because of the beat before it.

The plan must:

- Use the given value and enact its pattern in order across the beats, passing the catalog's shown-not-told test. Copy the value's pattern steps into `pattern` exactly as given.
- Follow one of the allowed structure templates, mapping its beats onto spreads roughly as its spread ranges suggest. Put the template id in `template`.
- Land the value at spread 9, 10 or 11 (`value_lands_at`): the hero's own choice, which costs something, is the turn. The child drives it; the companion helps, jokes and gets things wrong but does not solve it; adults are warm background.
- Use only cast ids and location names from the bible (settings are location names exactly as written). Start and end at or near home unless the template says otherwise; do not reuse a non-home setting from the previous episode.
- Respect the ledger: names, voices, objects where they were left, and threads that are still open. Reuse a running gag at most once. A callback is a reward, never a prerequisite: someone who never read an earlier episode must be able to follow this one.
- Keep scares within the band and resolve any mild scare within two spreads.
- Give every beat a concrete action, the emotional beat, a page-turn hook into the next spread (vary them; never two questions in a row), and the side of the spread kept quiet for text (`left` or `right`; alternate when it suits the composition).
- Spread 12 is quiet and echoes spread 1.
- `recap`: at most 60 words, what happened last time, for a reader who missed it (for episode 1, a one-line welcome to the world instead). `teaser`: one or two sentences that make next month irresistible, drawn from the ledger's next hook or the season loglines.
- Three grown-up questions a parent can ask after reading, open-ended and about the child's own life, never quizzing the moral.
=== user ===
Episode number: $episode

Value for this episode (catalog entry):
$value

Reader band rules:
$band

Allowed structure templates (the previous episode's template is excluded):
$templates

Continuity ledger:
$ledger

Previous episode (title, template, settings), or "none":
$previous
