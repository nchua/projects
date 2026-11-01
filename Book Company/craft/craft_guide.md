# Craft Guide v0

How our picture books are built. This file goes first in every writer prompt (SPEC §8.4) and is the house standard the judge and editor hold us to (§6.1). It is distilled from craft principles, not from any copyrighted text (D1). Keep it under two pages: if a rule needs a paragraph, it belongs in a template.

## 1. Structure

- **32 pages, 12 story spreads.** Spread 1 opens in the hero's ordinary world, with the want or problem stated by spread 2. The value lands in spreads 9–11, and spread 12 is the quiet ending. Recap and teaser spreads sit outside the 12 (§4.5) and the story never depends on them.
- **One story, one engine.** Every book uses one structure template (`structure_templates.yaml`) and one value pattern (`values_catalog.yaml`). The template gives the shape and the value gives the turn. Don't stack two problems.
- **Cause and effect, every spread.** Each spread happens *because of* the one before it. If you could swap two middle spreads without anyone noticing, one of them is filler.
- **The hero acts.** The child drives the decisive moment. Adults can be present and loving. The companion helps, jokes and gets things wrong, but it does not solve the story (rubric item 4).

## 2. Page turns

The page turn is the picture book's one special effect, so spend it on purpose.

- End each spread on a gap: a question, a half-finished action, a door about to open, a "But then…". The answer comes when the page turns.
- Put the surprise on the left of the next spread, so the reveal is the first thing the eye lands on.
- Vary the pull. Some turns are suspense ("Something was under the bed."), some are comic ("Toast had a plan. It was a terrible plan."), and some are emotional ("Maya didn't want to go home yet.").
- Never end two spreads in a row with a question.

## 3. Refrains

- Give each book one refrain: a short line of 3–8 words with a strong rhythm that the child can say before the adult reads it.
- Use it three or four times. Change it once, near the end, so the change carries the meaning ("Not yet, not yet" becomes "Now!").
- A refrain can be a sound ("*Tap. Tap. Kerplunk.*"), a companion catchphrase, or a question the hero keeps asking.
- Sound words go in italics in `read_aloud_notes`, so the reader knows to perform them.

## 4. The rule of three

- Three attempts, three places, three clues. The first sets the pattern, the second confirms it, and the third breaks it.
- Each attempt is harder or funnier than the last. In perseverance stories the hero changes method between attempts. Simply trying harder is not a change (§1.5).
- Keep the three structurally parallel (same sentence shape, same page position), so a child feels the pattern and enjoys it breaking.

## 5. Read-aloud

- Write for the grown-up's voice. Read every spread aloud before you keep it.
- Keep most sentences short and put the punch word at the end: "Under the leaf was a snail" is weaker than "Under the leaf, there was… a snail."
- Use one specific noun instead of two adjectives. Write "the red bucket with the crack", never "the big, colourful, wonderful bucket".
- Dialogue is short and sounds like a person. In band B, at most two speakers per spread.
- Stay inside the band's numbers (`band_rules.yaml`): words per book, sentences per spread, and the words-per-sentence cap.

## 6. Showing the value

- The value appears as a **choice the hero makes that costs something**. Never state it.
- Apply the catalog's shown-not-told test to the spread where the value lands. If a character names the lesson, rewrite the spread.
- Let another character's reaction carry the meaning: the friend's face, the companion going quiet, a parent's hand on a shoulder.
- No moral paragraph, no "and that's when she learned", no closing summary of what was learned (D10).

## 7. Endings

- **Echo the opening.** Repeat the first spread's image, place or line, changed by what happened.
- **Go quiet.** The final spread has the fewest words in the book, often one or two sentences. Use a calm image with no new information.
- Offer one small grace note: a callback joke, the refrain's last variation, or the companion doing something sweet.
- The teaser for next month comes after the ending, on its own spread. It never interrupts the ending.

## 8. Specificity and delight

- Each location gets one sensory signature: a smell, a sound, a texture. "The bakery smelled like warm toast and something burnt."
- Name things. Write "the wobbly blue stool", not "a chair", and "Mrs. Okoro's beagle", not "a dog".
- Earn at least two real laughs or surprises per book. Good sources are the companion's flaw, literal-minded misunderstandings, scale (a tiny thing causing a huge problem), and the hero being cleverer than the adults expect.
- Personal details from the profile are seasoning, not plot. One or two per book (the pet, the family's word for grandma) is plenty.

## 9. Writing for the illustrator

- Every spread has one picturable action. If you can't say what is drawn, the spread isn't finished.
- Leave the picture room to tell part of the story. Don't describe in text what the illustration already shows (colours, clothes, expressions), unless the words add something.
- Text is typeset, never painted in (D4). No signs, letters or labels that need to be read in the art.

## 10. What to avoid

- Morals, lessons and summaries of feelings ("She felt proud of herself").
- Anything in `banned_phrases.txt`, and the voice those phrases come from: breathless, glittery and vague.
- Magic that solves the problem. Magic can cause the problem or colour the world, but never fix it.
- Parents as obstacles or as rescuers. Parents are warm background.
- Scares beyond the band, lost or hurt parents, real brands, and real public figures.
- Rhyme, unless it is perfect in both rhythm and rhyme. Forced rhyme is worse than none.
- More than one exclamation mark per spread.
