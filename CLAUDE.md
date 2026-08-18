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
an `output_dir`, which defaults to `~/BookLabs/<book-slug>/` but can be
overridden per-invocation (see "Inputs" in `SKILL.md`). This repo stays
free of copyrighted book text, which is why it's public.

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
   general knowledge — not in generated exercises, not in any live
   `claude` CLI call the engine makes at runtime (`claude_review()`,
   `build_grading_prompt()`, `build_variant_prompt()`,
   `build_synthesis_prompt()` — every one of these explicitly instructs
   the model to judge/generate only from the excerpt(s) passed in, never
   general knowledge). This is the whole point of the tool: it teaches
   *this book's* approach, even where it diverges from convention. Any
   new runtime `claude` call must follow the same pattern.
3. **No reliance on external references even when they exist.** Some
   books ship official companion code (e.g. a GitHub repo). This skill
   deliberately never depends on that — it must work identically for any
   epub, including ones with no companion material anywhere.
4. **Zero required setup beyond `pandoc` and `python3`.** The engine
   itself is Python-stdlib-only — `venv` and `pip` are part of the
   standard toolchain, so a book declaring `dependencies` still doesn't
   add an external requirement, it just costs a one-time local install
   into that book's own `.venv`. Don't add a *required* third-party
   dependency to `server.py` itself without a strong reason — it breaks
   the "just clone and run" story in the README.
5. **Grading that needs a live LLM call goes through the `claude` CLI
   subprocess, never a raw Anthropic API key.** The CLI rides on the
   user's existing Claude Code login/subscription; a raw API key would
   be separate, metered billing. See `claude_review()`.
6. **Gating is enforced server-side, not just hidden in the UI.**
   `/api/submit`, `/api/self-assess`, `/api/grade-answer`, and
   `/api/skip` all check `is_unlocked()` before grading — this was a gap
   caught during initial testing, don't reintroduce it for new endpoints.
7. **Runtime-generated content (review variants, synthesis challenges)
   is ephemeral, never written to `content.json`.** `REVIEW_VARIANTS`
   and `SYNTHESIS_CHALLENGES` are in-memory dicts, gone on restart -
   that's deliberate. `content.json` is the one artifact the generation
   step produces and the one thing worth keeping stable; runtime
   variants exist purely to test retention with different specifics each
   time, and a synthesis challenge spans multiple blobs so it has no
   single blob to attach permanent state to. Don't persist either into
   the stored content pack.
8. **Structured `claude` CLI calls (grading/variant/synthesis) always
   degrade gracefully, never crash the request.** `call_claude_json()`
   returns `(None, error_message)` on any failure (CLI missing, timeout,
   unparseable output) instead of raising - callers check for `None` and
   return a clean error response (or, for `/api/review-due`, fall back
   to the static stored exercise) rather than letting an LLM hiccup break
   the endpoint.

## Design decisions and why (so they don't get re-litigated)

- **Implementation exercises by default; `short_answer` when code would
  be artificial busywork, or when the concept is fundamentally about
  interpretation rather than computation** (what a result means, why
  it's true, what it looks like geometrically — not just the formula
  that produces it) — and even then, prefer an applied/scenario question
  over pure recall. This came directly from the user wanting "learn by
  doing," not a quiz app; the interpretation clause was added after a
  math-heavy book (linear algebra demo) generated as 8/8 implementation,
  every blob framed as "implement a function" even for concepts whose
  point was geometric meaning (a zero dot product means orthogonal, a
  zero determinant means no unique solution) — implementable, but not
  actually testing whether that meaning was understood. See
  `SKILL.md`'s "Decide exercise type per blob."
- **Short-answer grading is claude-graded by default** (`/api/grade-answer`
  → `build_grading_prompt()`), with self-assessment (reveal + "I got it
  right"/"I missed it") kept as a manual fallback in the UI for when the
  `claude` CLI isn't available. Claude-grading gives a real verdict +
  specific feedback instead of asking you to judge your own answer; this
  only became viable once a live grounded grader was assumed reachable
  (see the conversation that led here - self-assessment was the
  original, more conservative default before that assumption held).
- **A "partial" verdict triggers one adaptive follow-up question**
  targeting exactly the gap identified, then finalizes on the second
  round regardless of verdict (`build_grading_prompt`'s
  `follow_up_question is not None` branch never asks a second follow-up).
  Bounded to one round deliberately - open-ended Socratic looping would
  be stronger pedagogically but unbounded cost/latency; one round is the
  practical middle ground.
- **Spaced review resurfaces a freshly generated variant of the blob's
  exercise** (`build_variant_prompt`, cached per-blob in
  `REVIEW_VARIANTS`), not a replay of the stored exercise - replaying the
  identical exercise risks testing memory of the specific answer rather
  than retention of the concept. Falls back to the static stored exercise
  if variant generation fails (see invariant 8).
- **Passing after a struggle (more than one attempt) keeps the Leitner
  box at 1 instead of advancing it** (`leitner_advance(..., struggled=)`,
  driven by `attempts` already tracked in `progress.json`) - eventually
  getting it right isn't the same evidence of retention as getting it
  right immediately, so a struggled concept comes back for review sooner
  than an easy one, not on the same schedule.
- **Synthesis challenges combine the 2-3 most recently passed blobs**
  (`recent_passed_blobs`, `build_synthesis_prompt`), generated on demand
  via `/api/synthesis-challenge`, graded through the same code-test or
  claude-grading paths as any other exercise. Requires at least 2 passed
  blobs (returns a 400 explaining why otherwise) - there's nothing to
  synthesize from just one concept.
- **Both spaced review and synthesis challenges are surfaced inline,
  between blobs, not just as separate on-demand modes.** The review
  banner (`checkReviewDue()`) now re-checks on every `refreshContent()`
  instead of only once at page load, so a review that becomes due mid-
  session shows up right after the blob that triggered it, not only on
  the next reload. A synthesis nudge (`renderCheckpointNudge()`) appears
  next to "Continue" whenever 2+ blobs are passed. Both stay strictly
  optional/non-gating - skipping either and clicking Continue has no
  cost - matching invariant 6 (only the primary exercise gates
  progression).
- **A failed synthesis challenge pulls its component blobs' next review
  forward to immediately due, but never moves their Leitner box**
  (`apply_synthesis_result()`, called from `/api/synthesis-submit`).
  Deliberately lighter than a direct review miss (which does reset the
  box via `leitner_advance`): struggling to combine several concepts
  together is weaker evidence against any one of them than missing a
  question aimed directly at it, but it shouldn't be a no-op either -
  before this, passing or failing a synthesis challenge had zero effect
  on spaced-review scheduling. A pass leaves everything untouched (not
  strong enough evidence to advance a box that a direct review didn't
  actually re-confirm).
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
- **Per-book dependency isolation via a lazily-created venv**
  (`ensure_venv()`, `<app_dir>/.venv`), not a shared global install and
  not Docker. This solves *dependency* isolation (no cross-book version
  conflicts, no global `pip install` pollution, trivial cleanup — delete
  the book's folder) — it is explicitly **not** a security sandbox: code
  still runs as the host user with full filesystem/network access, just
  through a different interpreter. If real security isolation (untrusted
  code, not just untrusted package lists) is ever needed, that's a
  separate, bigger decision (containers/VMs) — don't conflate the two.
- **Math rendering is KaTeX, vendored into `app-engine/static/vendor/katex/`**
  (~600KB: `katex.min.js`, `katex.min.css`, `contrib/auto-render.min.js`,
  woff2 fonts only — ttf/woff fallbacks dropped, every `@font-face` rule
  lists woff2 first so modern browsers never fetch them anyway), not a
  CDN — same "works fully offline" reasoning as everything else here.
  `app.js`'s `renderMath()` wraps `window.renderMathInElement` and gets
  called on every container that might contain book/generated/feedback
  text — see the call sites for the full list. The *editable* answer
  input deliberately does **not** auto-render while typing (would make
  editing your own LaTeX source impossible); a submitted answer only
  gets rendered back read-only, after grading, via `renderGradedResult()`.
- **`convert_epub.py` targets plain `markdown`, not `gfm`.** This
  mattered once math entered the picture: GFM serializes math in
  GitHub's own dialect (`` $`...`$ `` and fenced ` ```math ` blocks),
  not the `$...$`/`$$...$$` convention `renderMathInElement` is
  configured for. Plain `markdown` output uses `$...$`/`$$...$$`
  natively and was verified to produce identical output to `gfm` for
  everything else (headings, images, prose) — so this was a straight
  fix, not a tradeoff. Discovered by testing, not assumed: an earlier
  attempt at a LaTeX demo epub embedded literal `$...$` as plain HTML
  text rather than real `<math>` MathML, which pandoc's HTML reader
  treats as ordinary text and defensively escapes (`\$`, `\_`, `\|`,
  ...) when serializing — real math textbooks embed genuine MathML in
  their EPUB3 source, which pandoc recognizes as an actual Math AST
  node and serializes cleanly instead. `demo/linear-algebra-demo-book.epub`
  simulates that correctly (markdown-with-$...$ → pandoc → MathML →
  wrapped as the epub's XHTML), not with hand-typed dollar signs.

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
without needing a real book on hand), use one of the three hand-built,
self-authored, public-domain demo epubs — kept deliberately small so
they cost nothing to keep in git history:

```bash
python3 scripts/convert_epub.py demo/tiny-demo-book.epub /tmp/demo-out
python3 scripts/convert_epub.py demo/number-theory-demo-book.epub /tmp/demo-out-2
python3 scripts/convert_epub.py demo/linear-algebra-demo-book.epub /tmp/demo-out-3
```

`demo/tiny-demo-book.epub` (~3KB, 3 chapters/1 image, fables) exists
purely to exercise the converter (spine order, chapter naming, image
extraction/link-rewriting) — quick and disposable.

`demo/number-theory-demo-book.epub` (~7KB, 6 sections across 2
chapters/1 image, GCD+Euclidean algorithm+primes+modular exponentiation)
has enough real math/code content to be worth actually running through
phase 2 generation when testing generation-time changes (chunking,
exercise generation, prerequisites) or the runtime features that need
multiple related concepts to be meaningful (synthesis challenges, the
knowledge graph, dynamic review variants) — the 3-blob tiny-algorithms
`example_content.json` used by `test_engine.sh` is deliberately too
minimal for that.

`demo/linear-algebra-demo-book.epub` (~10KB, 8 sections across 3
chapters/1 image, vectors/dot products/matrices/determinants) exists
specifically to test math rendering end-to-end. Its section files embed
**real MathML**, not plain-text `$...$` — generated by piping markdown
source through `pandoc -f markdown -t html --mathml` (see
`SECTIONS_MD`/`md_to_xhtml_body` if you regenerate it), the same thing a
real publisher's EPUB3 toolchain produces. That distinction matters: it's
what exercises the `-t markdown` (not `-t gfm`) fix in `convert_epub.py`
correctly instead of accidentally testing something a real book would
never actually produce.

None of the three demos' generated `content.json` is committed here
(see the repo-scope note above) — generate it fresh into a scratch
`output_dir` when you need it for manual testing.

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
demo/number-theory-demo-book.epub bigger self-authored PD epub (math+code), for generation/feature testing
demo/linear-algebra-demo-book.epub biggest demo, real embedded MathML, for testing math rendering
app-engine/server.py              generic server: content, submit, hint, review, graph, progress
app-engine/static/                generic frontend (index.html, app.js, style.css)
app-engine/static/vendor/katex/   vendored KaTeX (math rendering), not a CDN
app-engine/content/SCHEMA.md      content.json spec
app-engine/content/example_content.json   worked 3-blob example (used by test_engine.sh)
```
