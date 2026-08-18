# CLAUDE.md

Context for a Claude Code session working *on this repo* (developing the
skill itself). For what the skill does and how a user runs it, see
`README.md`. For the step-by-step workflow the skill follows when
invoked on a book, see `SKILL.md`.

## What this repo is

A Claude Code skill (`book-to-lab`) that converts an epub into a local,
implementation-first learning web app. Two moving parts:

- **The engine** (`app-engine/`) — generic, book-agnostic. Same
  Python-stdlib server + plain HTML/CSS/JS frontend runs for every book.
- **The generation instructions** (`SKILL.md`) — what a Claude Code
  session does, live, when given a specific epub: converts it, then
  reads the converted markdown chapter by chapter and writes
  `content.json` (the one file that makes the engine specific to that
  book).

Generated book output (converted markdown + that book's copy of the app,
filled with real `content.json`) never lives in this repo — it goes to
`~/BookLabs/<book-slug>/` on whatever machine ran the skill. This repo
stays free of copyrighted book text, which is why it's public.

This repo lives at `~/Documents/created_skills/book-to-lab` and is
symlinked into `~/.claude/skills/book-to-lab` for discovery. Remote:
`https://github.com/loverawat/book-to-lab`.

## Invariants — don't break these without a reason

1. **The engine stays generic.** Nothing book-specific belongs in
   `server.py` or `static/`. If a change only makes sense for one book,
   it belongs in that book's `content.json`, not here. If you find
   yourself editing the engine to special-case something, that's a sign
   you actually need to extend the schema (affects every future book,
   fine) — not hardcode one book's needs (not fine).
2. **Exercises are grounded strictly in the source book.** No outside
   best practices, no "how I'd normally do this," no filling gaps from
   general knowledge — not in generated exercises, not in the `claude`
   CLI review prompt (see `claude_review()` in `server.py`, which
   explicitly instructs the reviewer to judge only against the passed-in
   excerpt). This is the whole point of the tool: it teaches *this
   book's* approach, even where it diverges from convention.
3. **No reliance on external references even when they exist.** Some
   books ship official companion code (e.g. a GitHub repo). This skill
   deliberately never depends on that — it must work identically for any
   epub, including ones with no companion material anywhere.
4. **Zero required setup beyond `pandoc` and `python3`.** The engine is
   Python-stdlib-only, no `pip install`. Don't add a dependency to
   `server.py` without a strong reason — it breaks the "just clone and
   run" story in the README.
5. **Grading that needs a live LLM call goes through the `claude` CLI
   subprocess, never a raw Anthropic API key.** The CLI rides on the
   user's existing Claude Code login/subscription; a raw API key would
   be separate, metered billing. See `claude_review()`.
6. **Gating is enforced server-side, not just hidden in the UI.**
   `/api/submit` and `/api/self-assess` both check `is_unlocked()`
   before grading — this was a gap caught during initial testing, don't
   reintroduce it.

## Design decisions and why (so they don't get re-litigated)

- **Implementation exercises by default; `short_answer` only when code
  would be artificial busywork** (e.g. a pure design tradeoff) — and
  even then, prefer an applied/scenario question over pure recall. This
  came directly from the user wanting "learn by doing," not a quiz app.
- **Short-answer grading is self-assessment (reveal + "I got it
  right"/"I missed it"), not automated NLP grading.** Keeps the engine
  dependency-free and honest — no fake precision from keyword matching.
- **Spaced review is a simple 5-box Leitner system** (`leitner_advance`,
  day-based intervals in `due_review_blob`), not a full SM-2
  implementation. Deliberately simple; revisit only if it proves too
  coarse in practice.
- **The knowledge graph is a prerequisite tree**, built purely from each
  blob's `prerequisites` list, walked 3-4 levels by `/api/graph`. It's a
  read-only browsing aid — looking at it never unlocks anything.
- **Generation happens chapter-by-chapter, written incrementally to
  `content.json`**, rather than holding the whole book in context at
  once. Books are long; this keeps each generation step tractable and
  resumable.
- **Local execution via subprocess, real interpreters** (not a sandboxed
  in-browser runtime like Pyodide) — chosen because exercises should be
  able to use real libraries, and this is a personal single-machine tool,
  not something meant to be shared/embedded as a public Artifact.

## Dev workflow

Run `scripts/test_engine.sh` after touching `server.py` before
committing — it spins up the engine against `example_content.json`,
exercises every endpoint (gating, submit pass/fail, locked-blob
rejection, hints, graph traversal, self-assessment, static serving),
asserts the responses, and tears itself down:

```bash
scripts/test_engine.sh
```

It's a regression check, not exhaustive — if you add a new endpoint or
field, add a `check` line for it in the same script rather than only
testing it manually.

For a full pipeline sanity check (epub → markdown → media → app,
without needing a real book on hand), use the tiny public-domain demo:

```bash
python3 scripts/convert_epub.py demo/tiny-demo-book.epub /tmp/demo-out
```

`demo/tiny-demo-book.epub` is a hand-built, self-authored 3-chapter/
1-image epub (~3KB) — kept deliberately tiny so it costs nothing to keep
in git history. It exists purely to exercise the converter (spine
order, chapter naming, image extraction/link-rewriting); it was never
run through phase 2 (content generation), so there's no matching
`content.json` for it.

`content.json` and `progress.json` under `app-engine/content/` are
gitignored on purpose — if `git status` ever shows them as untracked
changes ready to add, that's a sign a manual test run left them behind;
clean up before committing rather than adding them.

## Extending the schema

If you add a field to the content pack, update all four together or
they'll drift out of sync:

1. `app-engine/content/SCHEMA.md` — the spec
2. `app-engine/content/example_content.json` — a worked example using it
3. `app-engine/server.py` — if the engine needs to read/act on the new field
4. `SKILL.md` — the generation rules, so future generation runs actually produce it

## File map

```
SKILL.md                          workflow Claude follows per-book
README.md                         user-facing docs
LICENSE                           MIT
scripts/convert_epub.py           epub -> markdown + media (spine order, pandoc)
scripts/test_engine.sh            automated regression check for server.py
demo/tiny-demo-book.epub          tiny self-authored PD epub, for pipeline sanity checks
app-engine/server.py              generic server: content, submit, hint, review, graph, progress
app-engine/static/                generic frontend (index.html, app.js, style.css)
app-engine/content/SCHEMA.md      content.json spec
app-engine/content/example_content.json   worked 3-blob example (used by test_engine.sh)
```
