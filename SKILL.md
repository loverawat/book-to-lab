---
name: book-to-lab
description: Converts an epub book into an implementation-focused local learning web app - reading is chunked into small concepts, each paired with a hands-on exercise, gated progression, progressive hints, spaced review, and a prerequisite knowledge graph. Takes the epub path and an optional output folder (defaults to ~/BookLabs/<book-slug>/). Use when the user gives an epub and wants to learn it by building instead of just reading.
---

# book-to-lab

Turn a passive epub into an active, implementation-first local web app for
one specific book. This skill has two phases: a mechanical conversion
(scripted) and a generation phase that requires your judgment (no script
can do this part - it's genuine reading comprehension and exercise design).

## Inputs

- `epub_path`: path to the source `.epub` file (ask the user if not given).
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
├── media/                # extracted images, flat
├── manifest.json         # title, author, ordered chapter list
└── app/                  # the runnable web app for this book
    ├── server.py          # copied from app-engine/, unmodified
    ├── static/             # copied from app-engine/static/, unmodified
    └── content/
        └── content.json    # THIS is what you generate - see below
```

## Phase 1 - Conversion (mechanical, use the script)

```bash
python3 <skill_dir>/scripts/convert_epub.py <epub_path> <output_dir>
```

This unzips the epub, walks its spine (real reading order from the epub's
own manifest, not heading-guessing), converts each chapter to markdown via
pandoc, and copies+flattens all images into `media/` with links rewritten
to match. It writes `manifest.json` with the ordered chapter list.

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

Default to **implementation**. A blob's exercise is `short_answer` only
when forcing code would be artificial busywork - e.g. a pure design
tradeoff, a historical/motivational aside, a comparison of approaches
with no natural artifact to build. When in doubt, try harder to find an
implementation framing first (e.g. "implement both approaches and show
where they diverge" is usually possible even for tradeoff discussions).
When you do use `short_answer`, prefer an applied/scenario question over
pure recall.

### 3. Write the exercise, grounded strictly in this book

This is the most important constraint in the whole skill: **exercises,
hints, and reference solutions must come from what this chapter actually
teaches - not general best practice, not what you'd normally recommend,
not another book's approach to the same topic.** If the book's technique
differs from common convention, the book's technique is what the
exercise tests. Keep the `reading` field close to the book's own
wording/explanation rather than substituting your own generic summary.

For `implementation` exercises, write in the book's detected primary
language (check `content.json`'s top-level `"language"` field - default
to `"python"` if the book isn't language-specific; use `"javascript"` if
the book is clearly JS-focused). You must produce:
- `prompt` - what to build, in one or two sentences.
- `starter_code` - a stub with the right function signature, not a
  solution.
- `test_code` - a self-contained script that does
  `from solution import <name>` and asserts expected behavior, printing
  `ok` and exiting 0 on success. No network calls, no unseeded
  randomness. This is graded by literally running it - it must be
  correct and deterministic.
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
reference answer shown when the learner self-assesses - no auto-grading
needed, see the app's self-assessment flow).

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
