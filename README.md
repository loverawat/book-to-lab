# book-to-lab

A [Claude Code](https://claude.com/claude-code) skill that turns any epub
or PDF book into a local, implementation-focused learning web app: instead of
just reading, you get the concept in a small chunk, immediately build/do
something with it, and only move on once you've actually passed the
exercise. Past concepts resurface for spaced review as you go, and you
can pull up a "what do I need to know to understand this" prerequisite
graph for any concept, several levels deep.

## What it does

1. **Converts** your book into per-chapter markdown + a flat `media/`
   folder of images. For epub, using the epub's own spine (real chapter
   order), not heading-guessing. For PDF - which has no spine to read -
   chapter structure comes from the PDF's outline/bookmarks if it has
   one, or a best-effort heuristic if it doesn't (and that's flagged in
   `manifest.json` so the generation step knows how much to trust it);
   equations are detected by font and turned into images rather than
   garbled text, then transcribed into real LaTeX during generation.
   PDF conversion is inherently less reliable than epub's - prefer epub
   when you have the choice.
2. **Generates** a content pack for the book: each chapter broken into
   small concept "blobs," each paired with one primary exercise -
   `implementation` by default (in the book's own language, or just as
   a harness around a non-code skill - a SQL query checked by actually
   running it, a regex checked against real strings - when that's what
   the book is really teaching), `short_answer` for a discrete question
   with one right explanation, or `artifact` for producing, repairing,
   translating, or judging a concrete but non-executable thing (a
   design, a proof, a piece of applied writing, a counterexample) -
   plus progressive hints, a reference solution, and prerequisite
   links. Some blobs also get 0-2 optional supplementary questions, and
   where a concept is fundamentally about a process or transformation a
   still image can't capture, a generated diagram or animation.
3. **Runs** a local web app for that specific book: gated progression
   (finish the current exercise to unlock the next), a prerequisite
   knowledge graph per concept, and:
   - **Claude-graded answers** - type a response, get a real verdict and
     specific feedback grounded in the book, not just a self-check
     (covers both `short_answer` and `artifact` exercises). A "partially
     correct" verdict triggers one targeted follow-up question probing
     exactly the gap, instead of a flat right/wrong.
   - **Spaced review with fresh variants** - when a passed concept comes
     back for review, you get a newly generated variant (different
     inputs/scenario, same concept), not a replay of the exact exercise
     you already solved - so passing it again means something. A concept
     you struggled with (more than one attempt) comes back for review
     sooner than one you got right immediately, and if you missed an
     optional extra question on a concept, the next variant specifically
     re-probes that exact gap instead of just generically retesting it.
   - **Synthesis challenges** - combine your 2-3 most recently passed
     concepts into one exercise that requires using them together, not
     just recalling each in isolation. Offered inline between blobs once
     you've passed enough of them, or any time from the sidebar.
   - **Extra (optional) questions** - some blobs carry 0-2 supplementary
     questions beyond the one that gates progression. They never block
     you - offered once the primary exercise is passed, skipping costs
     nothing structurally - but getting one wrong pulls that concept's
     next review sooner and, unlike a skip, records what you missed so
     later review/synthesis exercises specifically target that gap.
   - **Book images, and generated diagrams where they help** - a
     relevant image the book itself shipped shows up in the reading
     pane; where a concept is fundamentally about a process or
     transformation a still image can't capture, generation can also
     produce a diagram or animation - judgment-gated, not added to
     every blob.
   - **Skip, reset, and shut down** from the sidebar - mark a concept
     known without redoing it (tracked separately from an actual pass),
     wipe a book's progress to start over, or stop the server, all
     without leaving the browser.
   - **Math rendering** - real LaTeX (`$...$`/`$$...$$`) in the reading
     pane, exercise prompts, hints, and feedback all get typeset via a
     vendored KaTeX (no CDN, works offline). Answers can mix plain
     English and LaTeX freely - grading reads for meaning either way -
     and a submitted answer is shown back to you rendered, next to the
     verdict.
   - **Tab-aware code editor** - Tab/Shift+Tab indent and outdent,
     Enter continues the previous line's indentation. Plain
     `<textarea>`s otherwise treat Tab as browser navigation, which
     makes writing code in them painful.

Everything generated - and every judgment the app makes at runtime -
is grounded strictly in that book's own text. No outside best practices
or other sources get mixed in, by design.

## How it's built

- `SKILL.md` - the instructions Claude Code follows when you invoke the
  skill. Conversion is scripted; chunking a chapter into concepts and
  writing exercises is done live, by Claude, because it genuinely
  requires reading comprehension - no script can do that part.
- `scripts/check_dependencies.py` - Phase 0 preflight, run before
  conversion starts: checks for `pandoc` (required) and `node`/`claude`
  CLI (optional, depending on the book), and prints the right install
  command for your platform if something's missing. Never installs
  anything itself.
- `scripts/convert_epub.py` - epub -> markdown + media, using only
  `pandoc` and the Python standard library.
- `scripts/convert_pdf.py` - PDF -> markdown + media, using `pymupdf`.
  Unlike everything else in this skill, that's a real third-party
  dependency - but it's scoped to this one script's own isolated venv
  (`<skill_dir>/.venv`, created automatically the first time you convert
  a PDF), not to the skill as a whole or to any generated book's app.
  Converting only epubs never touches it.
- `app-engine/` - the generic, book-agnostic local web app (Python
  stdlib server + plain HTML/CSS/JS frontend, no `pip install`, no
  build step - the one vendored exception is KaTeX in
  `app-engine/static/vendor/katex/`, included as files rather than a
  CDN so the app keeps working fully offline). The same engine runs
  every book; only `app-engine/content/content.json` differs per book.
  Its schema is documented in `app-engine/content/SCHEMA.md`, with a
  small worked example in `app-engine/content/example_content.json`.

Each book's generated output (converted text + its own copy of the app)
lands in `~/BookLabs/<book-slug>/`, independent of where the source epub
lives.

## Requirements

- [Claude Code](https://claude.com/claude-code)
- `pandoc` (`brew install pandoc`)
- `python3` (stdlib only, nothing to `pip install`)
- `node` - only if you convert a JavaScript-focused book (exercises run
  in the book's own primary language; Python is the default)
- Nothing extra to install for PDF input either - `pymupdf` is needed
  only by `scripts/convert_pdf.py`, and it's installed automatically
  into that script's own isolated venv the first time you convert a
  PDF (see "How it's built"). Converting only epubs never touches it.
- `claude` CLI on your `PATH` and logged in (rides on your existing
  Claude Code login/subscription, not a separate API key) - needed for
  most of what makes this "implementation-focused" rather than a plain
  quiz app: claude-graded `short_answer`/`artifact` answers (with
  adaptive follow-up), extra-question grading, dynamic spaced-review
  variants, synthesis challenges, and the optional "ask claude to
  review" button on code exercises. Without it: `implementation`
  exercises still auto-grade via real tests, `short_answer`/`artifact`
  fall back to manual self-assessment (reveal + self-report), spaced
  review falls back to replaying the stored exercise instead of a fresh
  variant, and synthesis challenges/extra questions return an error
  since there's no fallback for those. Progress, hints, and the
  knowledge graph never need it either way.

## Install

Skills are just directories with a `SKILL.md` in a location Claude Code
looks at. This repo can live wherever you keep code; make it discoverable
by symlinking it into your personal skills folder:

```bash
git clone <this-repo-url> ~/Documents/created_skills/book-to-lab
mkdir -p ~/.claude/skills
ln -s ~/Documents/created_skills/book-to-lab ~/.claude/skills/book-to-lab
```

(If you'd rather the working copy live directly under `~/.claude/skills`,
that's fine too - just `git clone` it straight there and skip the
symlink.)

## Use it

In a Claude Code session:

```
> use the book-to-lab skill on ~/Books/some-book.epub
```

Or run it directly from a terminal, without opening a session first -
this starts Claude Code pre-loaded with that instruction:

```bash
claude "use the book-to-lab skill on ~/Books/some-book.epub"
```

Either way works from any directory - skills in `~/.claude/skills/` are
discovered globally, not tied to a project folder. A `.pdf` path works
exactly the same way; conversion quality is just lower than epub's (see
"What it does" above).

By default everything for that book (converted markdown, media, and the
generated app) lands in `~/BookLabs/<book-slug>/`. To put it somewhere
else instead, just say so:

```
> use the book-to-lab skill on ~/Books/some-book.epub, output to ~/Desktop/my-book-lab
```

or from the terminal:

```bash
claude "use the book-to-lab skill on ~/Books/some-book.epub, output to ~/Desktop/my-book-lab"
```

Claude will convert the book, generate the exercises chapter by chapter
(this is the slow part for a long book - it's real reading + exercise
design, not a script), then start the local server and give you a URL
like `http://127.0.0.1:8420`.

To reopen a book you've already generated, you don't need the skill
again - just run its app directly:

```bash
cd <output_dir>/app && python3 server.py
```

If that book's exercises need third-party packages (say, a book about
pandas), the very first launch will pause for a few seconds to set up
an isolated environment just for that book (`<output_dir>/app/.venv`)
and install exactly what it needs there - not your system Python.
Every book gets its own, so different books can use different, even
conflicting, package versions without interfering with each other.
Deleting a book's output folder removes its dependencies with it -
nothing global ever gets touched.

## Adapting it to your own use case

- **Change what counts as "an exercise"** - edit the generation rules in
  `SKILL.md` (phase 2). This is the highest-leverage file: it's plain
  instructions, no code, so tightening/loosening the grounding rules,
  exercise-type criteria, or hint style is just an edit.
- **Change how the app looks or behaves** - edit `app-engine/` (the
  engine is shared across every book, so a change here applies the next
  time you generate or regenerate a book). `server.py` is a single
  dependency-free Python file; the frontend is plain HTML/CSS/JS with no
  build step.
- **Extend the content schema** (e.g. add a "further reading" field, a
  difficulty rating, multi-file exercises) - update
  `app-engine/content/SCHEMA.md`, `example_content.json`, `server.py`
  (if the engine needs to read the new field), and the generation rules
  in `SKILL.md` together, so all four stay in sync.
- **Copyright** - `~/BookLabs/<book-slug>/` contains the book's actual
  converted text. Keep that private; this repo (the skill itself) never
  contains book content, so it's fine to keep public.

## Testing changes

`scripts/test_engine.sh` runs the app engine against a worked example
and checks gating, hints, the knowledge graph, static serving, and the
grading paths that don't need a live model call (running tests against
real submitted code, self-assessment) - run it after any change to
`server.py`. It deliberately does **not** call the claude-dependent
endpoints (claude-graded `short_answer`/`artifact` answers, claude-graded
extra questions, dynamic review variants, synthesis challenges, the
"ask claude to review" button) - those need a real `claude` CLI call,
which would make the suite slow and non-deterministic. Verify those
manually against a real book (or the worked example) after touching
anything that builds their prompts.

Three self-authored, public-domain demo epubs let you sanity-check the
epub -> markdown + media conversion pipeline without needing a real
book on hand:

```bash
python3 scripts/convert_epub.py demo/tiny-demo-book.epub /tmp/demo-out
python3 scripts/convert_epub.py demo/number-theory-demo-book.epub /tmp/demo-out-2
python3 scripts/convert_epub.py demo/linear-algebra-demo-book.epub /tmp/demo-out-3
```

- `demo/tiny-demo-book.epub` (~3KB) - 3 short fables, one image. Good
  for a quick pipeline check.
- `demo/number-theory-demo-book.epub` (~7KB) - 6 sections across 2
  chapters on GCD/the Euclidean algorithm and primes/modular
  arithmetic, one image. Enough real math+code content to actually run
  through phase 2 generation and exercise the richer features (the
  prerequisite graph, synthesis challenges across concepts, dynamic
  review variants) rather than just testing the converter.
- `demo/linear-algebra-demo-book.epub` (~10KB) - 8 sections across 3
  chapters on vectors, matrices, and determinants, with real embedded
  MathML (not plain-text dollar signs - the same way a real math
  textbook's epub represents equations). Use this one to check the
  math-rendering pipeline specifically.

Three more, self-authored, for the PDF path specifically - each isolates
one part of what makes PDF conversion different from epub's:

```bash
python3 scripts/convert_pdf.py demo/pdf-demo-book.pdf /tmp/demo-pdf-out
python3 scripts/convert_pdf.py demo/pdf-no-outline-demo-book.pdf /tmp/demo-pdf-out-2
python3 scripts/convert_pdf.py demo/pdf-math-demo-book.pdf /tmp/demo-pdf-out-3
```

- `demo/pdf-demo-book.pdf` (~28KB) - a well-structured PDF with real
  outline/bookmarks and an embedded image. The "happy path" - checks
  outline-based chapter splitting, image extraction, and running
  header/footer stripping.
- `demo/pdf-no-outline-demo-book.pdf` (~4KB) - deliberately has no
  outline at all, to exercise the font-size/pattern heuristic fallback
  and confirm `manifest.json` correctly reports
  `"chapter_confidence": "heuristic"`.
- `demo/pdf-math-demo-book.pdf` (~8KB) - has one equation set in a font
  named like a real LaTeX math font (via a renamed, subsetted font file
  - there's no LaTeX distribution involved in building this fixture, it
  just exercises the same font-name-based detection code path a real
  LaTeX-produced PDF's math would). Checks that the equation gets
  rasterized into `media/` with a `[MATH: ...]` placeholder left in its
  place, rather than extracted as garbled text.

## License

MIT - see `LICENSE`.
