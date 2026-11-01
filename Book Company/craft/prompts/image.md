---
name: image
version: 1
---
Image prompt template for S7 and the bake-off. Not sent to Claude: `bookgen/stages/s07_generate.py`
renders the user section from a brief, the locked style and the appearance cards, and the
image adapter receives only that text plus the reference images (§8.6: adapters never see
craft text). The reference sheets carry each character's exact look; the words only name
who is who and pin the details models drift on (glasses, hair, outfit).
=== user ===
A children's picture-book illustration in this exact style: $style

Scene: $scene
Framing: $shot shot, at the child's eye level.
Characters (match each one's reference sheet exactly; nobody else in frame):
$characters
Continuity props that must appear: $props
Light and palette: $palette
Composition: keep the $text_area for typeset text: low detail, no faces or key action there.

Do not include: $negatives
