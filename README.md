# book-to-lab

A [Claude Code](https://claude.com/claude-code) skill that turns any epub
book into a local, implementation-focused learning web app: instead of
just reading, you get the concept in a small chunk, immediately build/do
something with it, and only move on once you've actually passed the
exercise. Past concepts resurface for spaced review as you go, and you
can pull up a "what do I need to know to understand this" prerequisite
graph for any concept, several levels deep.

## What it does

1. **Converts** your epub into per-chapter markdown + a flat `media/`
   folder of images, using the epub's own spine (real chapter order),
   not heading-guessing.
2. **Generates** a content pack for the book: each chapter broken into
   small concept "blobs," each paired with either a hands-on
   implementation exercise (default) or, only when code would be
   artificial, an applied short-answer question - plus progressive
   hints, a reference solution, and prerequisite links.
3. **Runs** a local web app for that specific book: gated progression
   (finish the current exercise to unlock the next), a prerequisite
   knowledge graph per concept, spaced review of things you've already
   passed, and an optional "ask claude to review my solution" button.

Everything generated is grounded strictly in that book's own text - no
outside best practices or other sources get mixed in, by design.

## How it's built

- `SKILL.md` - the instructions Claude Code follows when you invoke the
  skill. Conversion is scripted; chunking a chapter into concepts and
  writing exercises is done live, by Claude, because it genuinely
  requires reading comprehension - no script can do that part.
- `scripts/convert_epub.py` - epub -> markdown + media, using only
  `pandoc` and the Python standard library.
- `app-engine/` - the generic, book-agnostic local web app (Python
  stdlib server + plain HTML/CSS/JS frontend, no `pip install`, no
  build step). The same engine runs every book; only
  `app-engine/content/content.json` differs per book. Its schema is
  documented in `app-engine/content/SCHEMA.md`, with a small worked
  example in `app-engine/content/example_content.json`.

Each book's generated output (converted text + its own copy of the app)
lands in `~/BookLabs/<book-slug>/`, independent of where the source epub
lives.

## Requirements

- [Claude Code](https://claude.com/claude-code)
- `pandoc` (`brew install pandoc`)
- `python3` (stdlib only, nothing to `pip install`)
- `node` - only if you convert a JavaScript-focused book (exercises run
  in the book's own primary language; Python is the default)
- `claude` CLI on your `PATH` and logged in - only needed for the
  optional "ask claude to review" button; everything else (grading,
  hints, progress, the knowledge graph) works without it

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

By default everything for that book (converted markdown, media, and the
generated app) lands in `~/BookLabs/<book-slug>/`. To put it somewhere
else instead, just say so:

```
> use the book-to-lab skill on ~/Books/some-book.epub, output to ~/Desktop/my-book-lab
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
and checks gating, grading, hints, the knowledge graph, and static
serving all still work - run it after any change to `server.py`.

`demo/tiny-demo-book.epub` is a tiny (~3KB), self-authored,
public-domain 3-chapter epub with one image, used to sanity-check the
epub -> markdown + media conversion pipeline without needing a real
book on hand:

```bash
python3 scripts/convert_epub.py demo/tiny-demo-book.epub /tmp/demo-out
```

## License

MIT - see `LICENSE`.
