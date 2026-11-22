# Spec review loop

How a `draft` spec in this folder becomes `reviewed`. Claude runs this loop with fable before any build session starts. The build session (Opus) gets the spec file as its only context, so every gap left here becomes a guess there.

Run the whole loop each time a spec is reviewed, including a re-review after Nick changes direction.

## 1. Read and verify

- Read the whole spec. Then read `README.md` in this folder for the lifecycle rules.
- Check every claim the spec makes about existing code against the code: file paths, library pins, deploy config, test setup, formulas "ported from" another repo. A spec that says "same as the fitness backend" is checked against the fitness backend.
- Recompute anything numeric (fixtures, worked examples, limits). Do not trust a table because it looks precise.
- Run the spec's own examples through the spec's own rules. If the sample payload would be rejected by the validation it sits next to, that is a defect.

## 2. Attack it

Read as the implementer who will take every sentence literally, and as the user a week after launch. Look for:

- **Handoff blockers.** Things the build session cannot do: create a repo, reach a private service, spend money, hold a secret. Turn each into a prerequisite for Nick or a non-goal.
- **Contradictions.** Two sections that cannot both be true (a "never calls the model" rule beside a step that needs a model call; a rate limit the normal flow exceeds).
- **Undefined states.** A status, flag, or column that is written but never read, or read but never defined. Every state needs who sets it and what it changes.
- **Order dependence and silent loss.** Does the result depend on which input arrives first? Can a dedupe key, unique index, or "on conflict do nothing" drop real data without telling anyone?
- **Side effects on read.** A page load or GET that changes state will misfire on reload, prefetch, and retries.
- **Caps and counters.** Check each limit against a reload, a retry, a day boundary, and the timezone.
- **Ambiguous formulas.** "Use the difficulty" — the stored one or the updated one? Add a fixture that fails on the wrong reading.
- **Security basics.** Auth on every route (and the routes that must be public), brute force, untrusted text rendered as HTML, link schemes, secrets in logs, first-run account claims.
- **Missing escape hatches.** Wrong paste, forgotten password, bad card: is there a way to undo it without a database console?
- **Stale technology.** Model ids, SDK calls, and library pins age. Check current docs or skills rather than memory.
- **Scope.** Anything the first milestone does not need moves to a later one or to non-goals.

## 3. Ask Nick

- Ask only what is his to decide: where code lives, what costs money, product behavior with a real tradeoff, anything that reverses something he said. Decide the rest and record it.
- At most four questions per round. Each one stands alone, says what was found, names the options, and puts the recommended one first.
- If an answer shows the question was misunderstood, explain the mechanism in plain words and ask again. Do not pick for him.
- A changed direction (a new answer that reshapes the design) means going back to step 2 for the affected sections, not patching one line.

## 4. Rewrite

- Edit the spec so it can be built as written: decisions stated as decisions, defaults replaced by answers, prerequisites and non-goals explicit, acceptance criteria that would catch each defect found.
- Keep it self-contained. Restate what is needed from other repos; the build session may not have them.
- No secrets, real email addresses, or tokens.
- Fill in **Review notes** with: Nick's decisions, defects fixed, and things added. If requirement numbers changed, say so.
- Tick the reviewer checklist only for items that are now true. Mark every open question resolved, with who resolved it.

## 5. Save and hand off

- Set `status: reviewed` in the front matter, add a row to the spec's status log, and update the index in `README.md`.
- Commit and push to the branch the session was given. Do not open a pull request unless Nick asks.
- Tell Nick: where the spec was pushed, what he must do before starting the build session (prerequisites), what changed because of his answers, and the main risk that remains.

If review ends with a question only Nick can answer and no safe default, leave the spec `draft` and say what is blocking.
