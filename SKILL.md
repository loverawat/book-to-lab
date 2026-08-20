---
name: book-to-lab
description: Converts an epub or PDF book into an implementation-focused local learning web app - reading is chunked into small concepts, each paired with a hands-on exercise, gated progression, progressive hints, spaced review, and a prerequisite knowledge graph. Takes the book path and an optional output folder (defaults to ~/BookLabs/<book-slug>/). Use when the user gives an epub or PDF and wants to learn it by building instead of just reading.
---

# book-to-lab

Turn a passive epub or PDF into an active, implementation-first local web
app for one specific book. This skill has two phases: a mechanical
conversion (scripted) and a generation phase that requires your judgment
(no script can do this part - it's genuine reading comprehension and
exercise design).

PDF conversion is meaningfully less reliable than epub's - epub has a real
spine/manifest and (usually) semantic math markup; PDF has neither, so
chapter structure is inferred and math is detected/rasterized rather than
extracted as text. See Phase 1's PDF branch and CLAUDE.md for what that
means in practice and why. Prefer epub when both are available for the
same book.

## Inputs

- `book_path`: path to the source `.epub` or `.pdf` file (ask the user if
  not given). Which conversion script runs is determined by this file's
  extension - see Phase 1.
- `output_dir` (optional): where to put everything for this book - the
  converted markdown, media, and the generated app. If the user doesn't
  give one, default to `~/BookLabs/<book-slug>/`, where `<book-slug>` is
  a kebab-case slug of the book title (e.g. "Deep Learning with Python"
  -> `deep-learning-with-python`). If they do give one, use it exactly
  as given - don't nest it under `~/BookLabs/` or append a slug, since
  they've already told you where they want it.

Resolve `<output_dir>` once at the start (default or user-given) and use
that same path through every phase below - it's referred to as
`<output_dir>` for the rest of this document.

## Output location

Everything for this book goes in `<output_dir>`:

```
<output_dir>/
├── markdown/            # converted chapters, one file per chapter
├── media/                # extracted images, flat (+ rasterized math regions, PDF only)
├── manifest.json         # title, author, ordered chapter list, chapter_confidence (PDF only)
└── app/                  # the runnable web app for this book
    ├── server.py          # copied from app-engine/, unmodified
    ├── static/             # copied from app-engine/static/, unmodified files
    │   └── media/           # book images YOU copy here during Phase 2, only
    │                        # the ones actually referenced from content.json
    └── content/
        └── content.json    # THIS is what you generate - see below
```

## Phase 0 - Check dependencies (mechanical, use the script)

```bash
python3 <skill_dir>/scripts/check_dependencies.py
```

This checks for `pandoc` (required - Phase 1 can't run without it),
plus `node` and `claude` CLI (optional - only relevant to the book
you're about to generate, not to running this skill itself: `node` is
only needed if the book turns out JS-focused, `claude` is only needed
for the generated app's live grading/review/synthesis features, which
degrade gracefully without it per invariant 8 in `CLAUDE.md`).

- If a **required** tool is missing, the script exits non-zero and
  prints the exact install command for the detected platform. Stop
  here, show the user what's missing and the command to fix it, and
  offer to run it yourself via your own Bash tool - which will go
  through the normal confirm-before-running flow, not silently. Don't
  install anything without that confirmation (see invariant 9). Once
  it's installed, re-run the check before moving to Phase 1.
- If only **optional** tools are missing, don't block - just note it to
  the user in your final summary (e.g. "claude CLI wasn't found - live
  grading features in the app won't work until it's installed") and
  continue to Phase 1.

## Phase 1 - Conversion (mechanical, use the script)

Which script runs depends on `book_path`'s extension - everything after
this phase is identical regardless of which one ran, since both produce
the same `markdown/`/`media/`/`manifest.json` shape.

### If `book_path` ends in `.epub`

```bash
python3 <skill_dir>/scripts/convert_epub.py <epub_path> <output_dir>
```

This unzips the epub, walks its spine (real reading order from the epub's
own manifest, not heading-guessing), converts each chapter to markdown via
pandoc, and copies+flattens all images into `media/` with links rewritten
to match. It writes `manifest.json` with the ordered chapter list.

### If `book_path` ends in `.pdf`

```bash
python3 <skill_dir>/scripts/convert_pdf.py <pdf_path> <output_dir>
```

This has no epub-equivalent structural guarantees to lean on, so it does
its best mechanically and tells you how confident it is:

- **Chapter structure**: uses the PDF's own outline/bookmarks if present
  (as trustworthy as epub's spine). If there's no outline, falls back to
  a font-size + pattern heuristic (large, isolated, chapter-pattern-like
  lines) to guess chapter breaks. If that finds nothing usable either,
  the whole PDF becomes one chapter. `manifest.json` records which of
  these happened as `"chapter_confidence"`: `"outline"` / `"heuristic"`
  / `"none"`. **If it's not `"outline"`, treat the "chapter converts
  oddly, skim and use judgment" note below as required, not optional** -
  read through the actual chapter boundaries the heuristic produced
  before trusting them, and manually re-split (move text between chapter
  files, rename `manifest.json` entries) if a break is clearly wrong or
  clearly missing. A heuristic split is a guess, not a fact.
- **Math**: PDFs (unlike epub) essentially never have semantic math
  markup - text extraction of a real equation produces garbled text, not
  usable LaTeX. Spans set in a known math-typesetting font (Computer
  Modern, Latin Modern Math, STIX, etc.) are detected and rasterized to
  an image in `media/` instead, with a `[MATH: media/pdf_eq_NNN.png]`
  placeholder left in the markdown in their place. **When you hit one of
  these placeholders during Phase 2, read that image directly** (your
  Read tool handles images) and transcribe what it shows into real
  `$...$`/`$$...$$` LaTeX in the relevant `content.json` field - the same
  move already used for an epub that embeds an equation as a plain
  image, just now the default path for PDF math instead of a rare edge
  case. Only fall back to describing it in words (per the existing
  image-equation guidance below) if the rasterized image is genuinely
  illegible.
- Not every equation will be caught - the font-name detection only
  recognizes common LaTeX/professional-typesetting math fonts, not every
  way a PDF might embed math (e.g. Word's own equation editor uses
  different fonts entirely). If you notice garbled, clearly-mathematical
  text that wasn't flagged, treat it like an image-embedded equation:
  describe what it establishes in words using the surrounding prose,
  rather than guessing at a LaTeX transcription from garbled text.

Read `manifest.json` afterward to know how many chapters you have and
their titles - you'll need this for phase 2.

If a chapter converts oddly (some epubs have non-standard structure -
e.g. a "chapter" that's actually just a cover image, or front matter
mixed into chapter 1), skim the markdown output and use judgment about
what to skip (copyright page, index, ads) vs what to treat as real
content.

## Phase 2 - Content generation (your judgment - this is the real work)

Set up the app skeleton first:

```bash
mkdir -p <output_dir>/app/content
cp <skill_dir>/app-engine/server.py <output_dir>/app/server.py
cp -r <skill_dir>/app-engine/static <output_dir>/app/static
```

Then, **process the book chapter by chapter**, writing to
`<output_dir>/app/content/content.json` incrementally (read the
existing file, append, write back) rather than holding the whole book's
generated content in context at once - books are long, and this keeps
each step tractable and lets you resume if interrupted.

For each chapter's markdown file, in order:

### 1. Chunk into concept blobs

Break the chapter into small units - roughly "one idea per blob," not
"one blob per chapter." There's no fixed size: a dense technical chapter
might yield 8-10 blobs from a few pages; a discursive chapter might yield
3 from many pages. Use your judgment on what actually constitutes one
learnable concept in *this* book. Each blob needs a stable, globally
unique `id` (e.g. `ch03-b02`).

### 2. Decide exercise type per blob

Three types: `implementation`, `short_answer`, `artifact`. Default to
**implementation** - but read what that actually means below before
reaching for `short_answer`/`artifact` as an escape hatch; a lot of
concepts that don't look like "code" still belong in `implementation`.

**`implementation`** means "correctness is checkable by actually
running something" - and that's broader than it sounds, because the
book's detected language (`content.json`'s `"language"` field) only
needs to be the *harness*, not the skill being tested. If the book is
teaching SQL, the exercise can be "write the query," with `test_code`
executing it via `sqlite3` (stdlib) against a fixture and checking the
result - the learner is never asked to write Python, Python is just
what runs the check. Same idea for a regex checked via `re`, a config
file checked by parsing it, or any other non-Python skill a Python (or
JS) harness can mechanically verify. Don't default to "make them write
a Python function" just because Python is the book's detected
language - ask what skill the book is actually teaching first, then
decide what harness proves it.

**`short_answer`** is for a *discrete question with one right
explanation* - use it when forcing code would be artificial busywork
(a pure design tradeoff, a historical/motivational aside, a comparison
of approaches with no natural artifact to build) **or** when the
concept is fundamentally about interpretation rather than computation:
what a result *means*, why it's true, what it looks like geometrically,
what breaks if a condition fails. A blob can usually be *implemented*
(compute the dot product, multiply the matrices) without that exercise
ever testing whether the learner understands what the computed thing
represents - e.g. "implement the dot product" tells you nothing about
whether the learner knows a zero result means orthogonality, or why a
zero determinant means no unique solution. Don't force those into code
just because a plausible function signature exists; use `short_answer`
(teach-back framing, see below) instead. When in doubt between
`implementation` and `short_answer`, ask: does passing this exercise
actually require understanding the interpretation, or just
transcribing a formula? If the latter, prefer `short_answer`. This
matters most in math-heavy books, where most concepts have *both* a
computational side and an interpretive side - don't let every blob in
such a book default to implementation just because each one technically
has a formula to code. When you do use `short_answer`, prefer an
applied/scenario question over pure recall.

**`artifact`** is for producing, repairing, translating, or judging a
*concrete but inherently non-executable* thing - the core reframe:
"implementation" really means "produce a concrete artifact by applying
the concept," and code is just the special case where that artifact
happens to be executable. `artifact` is the non-executable case, graded
the same way as `short_answer` (claude-graded against the book's own
criteria, `reference_artifact` instead of `expected_answer`) but framed
as "build/fix/convert/judge X," not "explain X." Reach for it whenever
a concept's natural exercise is "produce something real" but nothing
can mechanically check it the way `test_code` checks code - don't force
it into a contrived function signature just to keep it in
`implementation`, and don't flatten it into `short_answer`-as-prose
either if there's a genuine artifact to produce. The categories below
cover most of what shows up in practice - the first set is "build it
from scratch," the second is a different cognitive mode (repair,
translation, judgment) that's often more diagnostic than fresh
production, since a learner can produce a correct-looking artifact by
pattern-matching the book's own example without understanding why it's
correct:

*Build from scratch:*
- **Manual worked derivation** - actually carrying out the procedure by
  hand (solve the equation, compute the statistic from given data, work
  the accounting entry, derive the proof step) rather than writing code
  that does it. Pedagogically different from coding it: code can hide a
  misunderstanding behind logic copied from a hint, typing out each step
  directly exercises procedural fluency.
- **Structured design artifacts** - a schema, an ER diagram, a system
  architecture sketch (Mermaid/ASCII), a component-responsibility list,
  a DDL statement. The book taught a design principle; the exercise is
  "design something using it," not "explain the principle." Natural for
  systems-design/database/architecture books.
- **Applied writing** - a paragraph, email, or argument that actually
  applies the specific technique just taught, not "explain the
  technique." Natural for rhetoric/communication/writing books, which
  otherwise have no implementation story at all.
- **Declarative/configuration artifacts** - a regex, a config file, a
  query, where the artifact itself is what's being taught and no
  Python/JS harness naturally exists to check it (if one does, that's
  `implementation` - see above).
- **Case-based application** - given a new scenario, apply the book's
  framework and produce a decision/plan with justification, not just
  describe the framework. Natural for strategy/negotiation/ethics/law
  books - this is where `artifact` for a non-technical book most
  naturally lives, since these books are inherently about applying a
  framework to situations, not computing anything.
- **Constructed formal objects** - a proof, a syllogism, a truth table,
  a labeled fallacy in a passage. Natural for logic/philosophy/discrete-
  math books - checkable structure, but not runnable code.

*Repair, translate, judge:*
- **Critique/repair** - give a flawed artifact (a buggy-but-non-code
  design, a broken argument, a proof with a subtle gap, a poorly
  structured plan) and have the learner find and fix what's wrong.
  Repairing a specific flaw requires knowing what it violates in a way
  producing a correct-looking artifact from scratch doesn't always
  require.
- **Representation translation** - convert the concept from the
  modality it was taught in into a different one: a word problem into
  an equation, a state machine into a table, prose into a flowchart, a
  formal proof into plain English (or the reverse). Rote copying
  doesn't survive a change of representation, so it's a strong test the
  underlying model actually transferred, not just the surface form.
- **Construct the counterexample, not the solution** - instead of
  solving a problem, construct an input that breaks a given claim, or a
  case where a property fails. Flips the usual direction and tests
  understanding of a concept's *boundaries*, not just its typical case.
- **Predict, then verify** - state a prediction (a sign, an order of
  magnitude, which of two outcomes) before doing the derivation/
  calculation. Surfaces misconceptions before they get papered over by
  the correct answer.
- **Ordering/sequencing** - given shuffled steps of a process (algorithm
  steps, a causal chain, order of operations), reconstruct the correct
  order and justify the dependency. Directly probes whether the learner
  understands *why* each step depends on the one before.
- **Rank/compare candidates** - given two or three candidate solutions
  to the same problem, rank them or pick the better one using the
  book's own stated criteria, and justify why. Tests evaluative
  judgment rather than production - a good fit where the book's actual
  point is "here's what separates good from bad."

*Where nothing digital can verify it:* books whose "hands-on" is
physically real (cooking, a craft, a workout) have no verification path
at all, code or otherwise. Don't invent a fake grading mechanism for
these - use `short_answer` with a self-report framing ("describe what
you did" + the existing reveal/self-assess fallback), not `artifact`.

None of this needs a new grading mechanism beyond what already exists -
`artifact` reuses the exact same claude-grading path as `short_answer`
(`build_grading_prompt`, adaptive one-round follow-up, self-assess
fallback). What's different is the prompt framing (produce/repair/
translate/judge X, not explain X) and the reference field
(`reference_artifact`, not `expected_answer` - see
`exercise_reference_text()` in `app-engine/server.py`).

### 3. Write the exercise, grounded strictly in this book

This is the most important constraint in the whole skill: **exercises,
hints, and reference solutions must come from what this chapter actually
teaches - not general best practice, not what you'd normally recommend,
not another book's approach to the same topic.** If the book's technique
differs from common convention, the book's technique is what the
exercise tests. Keep the `reading` field close to the book's own
wording/explanation rather than substituting your own generic summary.

If the chapter contains real mathematical notation, write it as LaTeX
using `$...$` for inline math and `$$...$$` for display equations in
`reading`, `prompt`, `hints`, and `expected_answer` - the app renders
this (KaTeX) in every place these fields are shown. If the source epub
represents an equation as an image rather than as text/MathML, read that
image directly (in `media/`, linked from the markdown) and transcribe it
into LaTeX the same way described for PDF math placeholders in Phase 1 -
don't skip it silently. If it's illegible even as an image, fall back to
describing in `reading` what the equation establishes in words; the
surrounding prose usually makes that possible.

If the chapter's markdown references a real (non-math) image
(`![...](media/<file>)`) near this blob's source content, and it
actually illustrates the concept - not decorative, not unrelated, not
already redundant with the prose - copy that file from `<output_dir>/media/`
into `<output_dir>/app/static/media/` (create the directory the first
time you need it) and add `<img src="media/<file>" alt="...">` to
`reading_html`. The engine already serves anything under `app/static/`,
so this needs no code change, just the file being copied to where it's
reachable - see "Referencing book images" in
`app-engine/content/SCHEMA.md`. Don't copy every image that happens to
be nearby in the source; most images near a paragraph aren't the point
of that paragraph. Images already consumed as `[MATH: ...]` placeholders
are different - those get transcribed into LaTeX text per the paragraph
above, never also embedded as images here.

**Optionally, generate a diagram or animation** - but only where a
visual genuinely clarifies something the prose doesn't; this is not a
per-blob default, the same way not every blob needs an implementation
exercise forced onto it. When you're considering one, classify the
concept first:

- **Static** (what does X look like, a labeled structure, a spatial
  layout) - a relevant book image (per the paragraph above) already
  covers this as well as anything generated could. Only generate
  (inline SVG, see below) when no useful book image exists for it.
- **Process/transformation** (how does X become Y, what happens as you
  vary Z, watching a matrix deform a grid, a proof constructing itself)
  - a still image, even the book's own, can only show a snapshot or a
  before/after pair; it can't show the transformation happening. Don't
  let "the book already has an image here" end the discussion for this
  category - ask instead whether understanding genuinely depends on
  watching the process unfold, or whether the endpoints alone (which a
  still image already shows) are enough. If the process itself is the
  hard part, generate an animation even when a book image already
  exists for this concept - keep the book's own image too if it's
  otherwise relevant (it still carries the book's own labels/notation
  and is what the surrounding prose refers to); the animation adds the
  motion dimension on top, it doesn't have to replace anything.

When you do generate, default to **hand-authored inline SVG** in
`reading_html` (`<style>` with `@keyframes` for any motion) - it's just
markup, no execution, no dependency, same as any other HTML in
`reading_html`. Only execute a script instead when hand-computed SVG
coordinates would be genuinely error-prone - plotting a real function's
curve, a numerically accurate vector/transformation diagram - where
correctness depends on an actual computation, not something you can
eyeball. In that case:

```bash
python3 -m venv <skill_dir>/.venv          # only if it doesn't exist yet
<skill_dir>/.venv/bin/python3 -m pip install --quiet matplotlib pillow   # only if not already installed
```

This is the same isolated skill-tooling venv `convert_pdf.py` uses for
`pymupdf` (see `CLAUDE.md`) - reuse it rather than creating another one;
neither `matplotlib` nor `pillow` are per-book or engine dependencies,
they're tooling this generation step itself needs, gone once the image
is produced. Write your script, run it with
`<skill_dir>/.venv/bin/python3`, save a static PNG (or an animated GIF,
via `matplotlib.animation` + Pillow's `PillowWriter`, which needs no
`ffmpeg`) into `<output_dir>/app/static/media/`, and reference it the
same way as a book image: `<img src="media/<file>" alt="...">`. Look at
the result before committing to it - if it doesn't actually clarify the
concept, don't include it just because you generated it.

For `implementation` exercises, write in the book's detected primary
language (check `content.json`'s top-level `"language"` field - default
to `"python"` if the book isn't language-specific; use `"javascript"` if
the book is clearly JS-focused) - or, if the book's actual skill is
something a Python/JS harness can check rather than Python/JS itself
(see "Decide exercise type per blob" above), `starter_code`/
`reference_solution` hold that other skill's real syntax (a SQL string,
a regex, a config block) as plainly as possible, with just enough
Python/JS wrapper for `test_code` to run and check it - the harness
language is scaffolding, not the point of the exercise. You must
produce:
- `prompt` - what to build, in one or two sentences.
- `starter_code` - a stub with the right function signature, not a
  solution.
- `test_code` - a self-contained script that does
  `from solution import <name>` and asserts expected behavior, printing
  `ok` and exiting 0 on success. This is graded by literally running it.
  No network calls. Where it's natural (not every exercise), generate
  random valid inputs seeded from the `BOOK_TO_LAB_SEED` environment
  variable and check correctness against a property or a small reference
  computation rather than one fixed input/output pair - see "test_code"
  in `app-engine/content/SCHEMA.md` for the full rule and why (it stops
  a submission passing by matching memorized values instead of actually
  solving the general problem).
- `hints` - 2-4 hints, ordered gentle -> specific -> near-solution.
- `reference_solution` - a real, correct solution matching the book's
  approach.

If `test_code`/`starter_code`/`reference_solution` for a Python book
import anything beyond the standard library (e.g. `numpy`, `requests`),
add that package name to the top-level `dependencies` array in
`content.json` (dedupe as you go - most books converge on a small,
stable set after the first few chapters). Leave it empty for books that
only need the standard library. This is what lets the engine run that
book's exercises in their own isolated per-book environment instead of
your system Python - see "Per-book dependency isolation" in
`app-engine/content/SCHEMA.md`.

For `short_answer` exercises, write `prompt` and `expected_answer` (the
reference answer used both when the learner self-assesses and when the
app grades their typed answer with `claude`, grounded in `reading` -
see `claude_grade`/`build_grading_prompt` in `app-engine/server.py`).
When the concept is a design rationale, a tradeoff, or a "why" rather
than a discrete fact, prefer framing the prompt as a teach-back
question - "explain X in your own words as if teaching someone
unfamiliar with it" - rather than a narrow recall question. Teach-back
prompts are graded the same way as any other `short_answer` exercise;
this is a matter of how you phrase `prompt`, not a different schema
field.

For `artifact` exercises, write `prompt` and `reference_artifact` (same
role as `short_answer`'s `expected_answer` - the grounding reference for
self-assessment and for `claude`-grading, never shown to the learner
directly). Phrase `prompt` as an instruction to produce/repair/
translate/judge something concrete (see the categories above), not as a
question to answer - that framing difference is what actually
distinguishes this from `short_answer` in the learner's experience,
since both are graded through the identical mechanism.

**Optionally, add `extra_questions`** (0-2, same object shape as
`exercise` above, authored the same way per its own `type`) - but only
where a second question genuinely earns its place, not as a default.
It earns its place when the primary exercise necessarily leaves
something real on the table: the primary is `implementation` but the
concept also has a real interpretive angle worth checking (what does
the result *mean*, not just whether it computes correctly - the same
distinction that drives the `short_answer`-vs-`implementation` choice
above, now applied as a supplement rather than a replacement); or the
concept has a natural related-but-distinct variation worth testing
separately (a different edge case, a related operation) that would be
artificial to cram into the one primary exercise. It does *not* earn
its place just to pad out a blob, or to test the same thing the primary
already tests with different numbers - that's busywork, not a second
question. Most blobs shouldn't have any. These are strictly optional
for the learner too - the frontend offers them once the primary is
passed, never blocks on them, and correctness has no bearing on
progression - only a bearing on this blob's own spaced-review timing
and, when a question is answered incorrectly, on what a later review
variant specifically re-probes (see "Extra (optional) questions" in
`app-engine/content/SCHEMA.md` for the mechanism - nothing further to
do here beyond authoring good questions when they're warranted).

### 4. Set prerequisites for the knowledge graph

For each blob, list the `prerequisites` (blob ids) a learner should
already understand. Usually the immediately preceding blob or two, but
also reach further back when a concept genuinely depends on something
from an earlier chapter (e.g. chapter 5 reusing a chapter 2 concept).
This is what the app's "prerequisites for this concept" graph walks,
3-4 levels deep - so it's worth being accurate here, not just chaining
sequentially.

### 5. Append to content.json

Merge this chapter's blobs into the running `content.json`
(`{title, language, dependencies, chapters: [{id, title, blobs: [...]}]}`),
matching the schema documented in `app-engine/content/SCHEMA.md`.
Validate it's well-formed JSON before moving to the next chapter.

## Phase 3 - Run it

```bash
cd <output_dir>/app && python3 server.py
```

Report the local URL (default `http://127.0.0.1:8420`) to the user. The
"ask claude to review" button in the app shells out to the `claude` CLI
on the user's PATH (their existing Claude Code login/subscription, not a
separate API key) - no setup needed beyond having `claude` installed.

If `content.json` has a non-empty `dependencies` list, this first
startup will pause briefly to create `<output_dir>/app/.venv` and
install them - mention that to the user so a several-second delay on
first launch isn't mistaken for a hang.

## Notes

- The app engine (`server.py` + `static/`) is generic and must not be
  edited per-book - if something book-specific is needed, it belongs in
  `content.json`, not the engine. If you find yourself wanting to modify
  the engine for one book, that's a signal that either the schema needs
  extending (edit `app-engine/` in the skill itself, benefiting every
  future book) or you're about to break "stick to the source material."
- Progress (`app/content/progress.json`) is created at first run and is
  specific to that book/machine - don't generate or hand-write it.
- Re-running phase 2 on a book you've already generated will overwrite
  `content.json`; if the user wants to regenerate, confirm first since it
  doesn't preserve their progress mapping if blob ids change.
