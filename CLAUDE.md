# CLAUDE.md

Context for a Claude Code session working *on this repo* (developing the
skill itself). For what the skill does and how a user runs it, see
`README.md`. For the step-by-step workflow the skill follows when
invoked on a book, see `SKILL.md`. For open ideas and possible future
work not yet committed to, see `FUTURE_WORK.md` — check it before
starting speculative/exploratory work, and add to it rather than losing
an idea discussed in conversation but not acted on.

## What this repo is

A Claude Code skill (`book-to-lab`) that converts an epub or PDF into a
local, implementation-first learning web app. Two moving parts:

- **The engine** (`app-engine/`) — generic, book-agnostic. Same
  Python-stdlib server + plain HTML/CSS/JS frontend runs for every book.
- **The generation instructions** (`SKILL.md`) — what a Claude Code
  session does, live, when given a specific book: converts it, then
  reads the converted markdown chapter by chapter and writes
  `content.json` (the one file that makes the engine specific to that
  book).

Conversion (Phase 1) is genuinely two independent scripts —
`convert_epub.py` and `convert_pdf.py` — but generation (Phase 2) is not
input-format-aware at all: both scripts produce the identical
`markdown/`/`media/`/`manifest.json` shape, so everything after Phase 1
works the same regardless of which one ran. All of PDF's real complexity
(structure inference, math-as-image) is quarantined inside
`convert_pdf.py`; see its design-decisions entries below before touching
either conversion script.

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
   the "just clone and run" story in the README. This is now *verified*
   rather than silently assumed: `scripts/check_dependencies.py` runs as
   `SKILL.md`'s Phase 0 and checks for `pandoc` (required) plus `node`
   and `claude` CLI (optional — known dependencies of specific features,
   not of the skill itself: `node` only if the book turns out
   JS-focused, `claude` only for the generated app's live grading/
   review/synthesis, which already degrades gracefully without it per
   invariant 8).
5. **Grading that needs a live LLM call goes through the `claude` CLI
   subprocess, never a raw Anthropic API key.** The CLI rides on the
   user's existing Claude Code login/subscription; a raw API key would
   be separate, metered billing. See `claude_review()`.
6. **Gating is enforced server-side, not just hidden in the UI.**
   `/api/submit`, `/api/self-assess`, `/api/grade-answer`, and
   `/api/skip` all check `is_unlocked()` before grading — this was a gap
   caught during initial testing, don't reintroduce it for new endpoints.
   `/api/extra-submit` and `/api/extra-skip` extend this a step further:
   they check `is_unlocked()` *and* that the blob's primary `exercise`
   is already `"passed"` — extra questions are offered in the UI only
   once the primary is passed, and that precondition is enforced
   server-side too, not just by hiding the button.
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
9. **Dependency installation is proposed, never silent.**
   `scripts/check_dependencies.py` may detect a missing tool and print
   the right install command for the platform, but it must never run a
   package manager unprompted, and `SKILL.md`'s Phase 0 instructions say
   so explicitly. Running one is a hard-to-reverse, often-sudo-requiring
   action — offering to run it through Claude Code's own confirm-before-
   running flow is the mechanism, not a background retry loop. Don't
   reintroduce silent auto-install for convenience.

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
  `venv_python()` checks both the POSIX (`bin/python3`) and Windows
  (`Scripts/python.exe`) venv layouts rather than branching on
  `sys.platform` — it previously only checked the POSIX path, so on
  Windows the interpreter was never found. `ensure_venv()` had the same
  problem one level up: it resolved `pip` via a hardcoded
  `VENV_DIR / "bin" / "pip"` and ran it with `check=True`, uncaught, in
  `main()` — so on Windows this wasn't a graceful fallback, it crashed
  the server outright on startup for any book with declared
  `dependencies`, before ever printing "book-to-lab running at...".
  Fixed by switching to `<interpreter> -m pip install ...` through
  `venv_python()` instead of resolving a separate pip path — sidesteps
  needing a second POSIX/Windows lookup entirely. `ensure_venv()` also
  now gates on `VENV_DEPS_MARKER` (a file written only after `pip
  install` actually succeeds), not on `VENV_DIR` existing — venv
  creation happens before packages are installed into it, so an
  interrupted first run (network blip, Ctrl+C, one bad package name)
  used to leave a venv that looked "already set up" forever, with the
  missing packages only ever surfacing later as a confusing
  `ModuleNotFoundError`; now a missing marker triggers a retry that
  reuses the existing interpreter instead of recreating the venv.
  Verified end-to-end (fresh install, recovery from a simulated
  interrupted install, and a no-op third run) against a real throwaway
  dependency (`six`) on macOS; the Windows-specific paths in both
  functions are still logic-verified only, not run on an actual Windows
  machine — none was available to verify against.
- **`scripts/check_dependencies.py` is a flat, hardcoded list of exactly
  the tools this skill depends on** (`pandoc`, `node`, `claude` CLI —
  not `python3`, which the script needs just to run, so its own absence
  can't be reported by it), not a general package-manager abstraction.
  Deliberately not built: distro detection across
  apt/dnf/pacman/zypper/apk (some Linux systems have several installed
  at once, so "detect the right one" isn't reliably answerable, and a
  flat "here's the Debian/Ubuntu command, otherwise see the docs" covers
  the realistic case at a fraction of the complexity), and support for
  multiple Windows installer ecosystems (winget/Chocolatey/Scoop) as
  interchangeable — winget is what's built into modern Windows, that's
  the one suggested. Add a tool to the list when a real feature needs
  it, not preemptively (see invariant 4, and the still-open "relaxing
  invariant 4" question in `FUTURE_WORK.md`).
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
- **`convert_pdf.py` gets its own isolated venv, separate from both
  invariant 4 and any book's per-book venv** (`<skill_dir>/.venv`,
  self-bootstrapped by the script itself via `_relaunch_in_skill_venv()`
  before it ever imports `pymupdf`). This is a third category, distinct
  from the other two venvs already in this codebase: the per-book venv
  (`ensure_venv()` in `server.py`) isolates a *generated book's exercise*
  dependencies; this one isolates a dependency of the *skill's own
  conversion tooling*, used once at Phase 1, never touched by the
  running app or any book's exercises. Mixing it into the per-book venv
  would conflate two different lifecycles and consumers. Converting only
  epubs never creates this venv or needs `pymupdf` at all.
  Installing `pymupdf` here is *not* gated behind the guided-install
  flow (invariant 9) the way `pandoc`/`node`/`claude` are — that
  distinction matters: invariant 9 is about system-level package-manager
  actions (often sudo, hard to reverse); a `pip install` into a private,
  trivially-deletable venv is neither, and `ensure_venv()` already
  installs a book's own declared dependencies the same way, without
  asking. Only the venv-*python* check needed the fix
  `venv_python()` got — see below.
- **`convert_pdf.py` detects "am I already running inside the skill
  venv" via `sys.prefix`, not by comparing `sys.executable` paths.**
  Found by testing, not assumed: a venv's own interpreter binary is
  typically a symlink back to the base Python install, so
  `Path(sys.executable).resolve()` collapses to the *same file* whether
  or not the venv is active, making a path-equality check always true
  and silently skipping the re-exec into the venv entirely.
  `sys.prefix` reflects which environment's site-packages is actually
  active regardless of that symlink, and doesn't have this problem.
- **PDF chapter structure is inferred in three tiers, most-trustworthy
  first, with the result recorded as `chapter_confidence` in
  `manifest.json`**: the PDF's own outline/bookmarks
  (`get_outline_chapters`) if present — as trustworthy as epub's spine;
  a font-size + regex-pattern heuristic (`find_heading_candidates`) if
  not, requiring two corroborating signals (meaningfully larger than
  body text size *and* either a chapter-like pattern or dramatically
  larger) before flagging a heading candidate, to avoid treating every
  bolded pull-quote as a chapter start; a single whole-document
  "chapter" as the last resort. The confidence value exists so Phase 2
  knows how much to trust the split it's been handed — see `SKILL.md`'s
  PDF branch, which upgrades the epub-era "skim and use judgment" aside
  into a required step whenever confidence isn't `outline`. Not treated
  as a failure state: Phase 2 already does judgment-based concept
  chunking within a chapter regardless of size, so a coarse single-
  chapter split degrades gracefully rather than breaking anything.
- **Running header/footer detection (`find_boilerplate_lines`) must be
  computed document-wide, not per-chapter.** Found by testing, not
  assumed: an early version computed it while assembling each chapter
  individually, and a 2-page chapter's page-number footer never had
  enough occurrences (needs ≥3, or ≥40% of pages) to be recognized as
  boilerplate — it only ever repeats often enough to detect across the
  *whole* document. Fixed by extracting every page once up front in
  `main()`, computing the boilerplate set from all of it, then having
  each chapter's assembly step only slice and filter that pre-extracted
  data rather than re-deriving its own local signal.
- **Per-page extraction returns one combined list of `(plain_text,
  markdown_text)` pairs, not two separately-grown parallel lists.**
  Found by testing, not assumed: an earlier version kept `plain_lines`
  and `md_parts` as two lists built in the same loop, but an image block
  only appended to `md_parts` (it has no plain-text line of its own) —
  so on any page containing an image, the two lists silently drifted out
  of index alignment, and boilerplate-line filtering silently corrupted
  for everything after the image on that page (a real running footer
  stopped being recognized). One combined list, growing one entry per
  line/image in lockstep, makes that class of bug structurally
  impossible rather than something to keep getting right by convention.
- **PDF math is detected by embedded font name and rasterized to an
  image, not extracted or reconstructed as text** (`is_math_font`,
  `MediaWriter.save_math`) — real math-typesetting font families
  (Computer Modern, Latin Modern Math, STIX, etc.) are a decades-stable,
  well-documented naming convention, and a PDF's extracted text for an
  equation is otherwise just garbled glyph order with no fraction/
  exponent structure. Deliberately *not* attempting automated LaTeX
  reconstruction (Mathpix-style OCR, or a local math-OCR model) — that
  would be a real new dependency (an API, or a heavy ML model) for a
  problem that already has a good answer: Phase 2 generation is done by
  a live, multimodal Claude Code session, so it can just read the
  rasterized equation image directly (`Read` already handles images)
  and transcribe it into LaTeX itself, extending the existing epub
  image-equation fallback rather than building new machinery. See
  `SKILL.md`'s PDF branch. The font-name list is implemented from
  documented naming conventions and validated against a synthetic test
  (a real font file renamed via `fontTools` to a known math-font name,
  see `demo/pdf-math-demo-book.pdf`) that exercises the same detection
  code path — **not** verified against a real LaTeX-produced PDF, since
  no LaTeX distribution was available to generate one in this
  environment. Won't catch every way a PDF embeds math (e.g. Word's own
  equation editor uses different fonts); `SKILL.md` tells the generation
  session to fall back to describing garbled-but-clearly-mathematical
  text in words if it notices detection missed something.
- **PDF demo fixtures are self-authored via `pymupdf` directly, not
  built from a real book** (`demo/pdf-demo-book.pdf`,
  `demo/pdf-no-outline-demo-book.pdf`, `demo/pdf-math-demo-book.pdf`) -
  same reasoning as the epub demos (public-domain, deliberately small,
  each isolates one thing: real outline + image + header/footer
  stripping; no outline at all; one math region). The math demo's font
  was produced by taking a real system font file and renaming its
  internal name-table records to a known math-font name via `fontTools`
  (subsetted down to just the glyphs used, ~5KB, to keep the fixture
  small) - this validates the font-name-detection code path faithfully
  but is not the same as validating against a document real LaTeX
  actually produced.
- **Book images are copied into `app/static/media/` during Phase 2,
  not served from the sibling `<output_dir>/media/` directly.** Both
  `convert_epub.py` and `convert_pdf.py` extract every image into
  `<output_dir>/media/`, but that trail used to end there - `SKILL.md`
  never instructed referencing them, and `server.py`'s static handler
  only serves `app/static/`, so every extracted image sat unused. Fixed
  by having Phase 2 copy the *specific* images it actually decides to
  use into `app/static/media/` and reference them from `reading_html`
  as a normal `<img src="media/<file>">` — zero engine changes, since
  the existing static handler already serves anything under
  `app/static/`. Deliberately not the alternative (extending
  `server.py` to also serve the sibling `media/` directory): that would
  make the engine depend on output-layout knowledge it doesn't
  currently have, against invariant 1, for a problem generation-time
  copying already solves without touching the engine at all. Also means
  curation is free: only images Phase 2 judges actually relevant to a
  blob get copied, not every image that happened to be nearby in the
  source markdown - see `SKILL.md`'s Phase 2 and "Referencing book
  images" in `app-engine/content/SCHEMA.md`.
- **Generated diagrams/animations are classified static vs.
  process/transformation before deciding whether a book image already
  covers it.** For a static concept (what does X look like), a relevant
  book image wins outright - generating one is only a fallback for when
  none exists. For a process concept (how does X become Y), a still
  image - even the book's own - can only show a snapshot or a
  before/after pair, not the transformation itself; whether a book
  image already exists for it doesn't settle whether an animation is
  worth generating too. Both can coexist: the book's own image still
  carries its own labels/notation and is what the surrounding prose
  refers to, the generated animation adds the motion dimension a still
  image structurally can't. Judgment-gated either way, same failure
  mode as `short_answer` eligibility and image-referencing before it -
  this is not a per-blob default.
- **Diagram generation defaults to hand-authored inline SVG (+CSS
  `@keyframes` for motion), only executing a script when hand-computed
  coordinates would be genuinely error-prone** (a real function's
  curve, a numerically accurate transformation) - and there, `matplotlib`
  + Pillow's `PillowWriter` (animated GIF, no `ffmpeg` needed) over
  Manim, which needs system-level dependencies a pip-only venv can't
  install (still gated behind the still-open invariant-4 question in
  `FUTURE_WORK.md`). When a script does run, it reuses the *same*
  isolated skill-tooling venv `convert_pdf.py` already created for
  `pymupdf` (`<skill_dir>/.venv`) rather than a separate one -
  `matplotlib`/`pillow` are generation-time tooling, not a per-book or
  engine dependency, exactly the same category `pymupdf` is; one shared
  venv for that category beats one per tool. The output (a static PNG
  or GIF) is saved into `app/static/media/` and referenced exactly like
  a book image - no schema change, no engine change.
- **`extra_questions` (0-2 per blob) are authored supplementary
  questions that never gate progression, but aren't consequence-free
  either** - only the blob's one `exercise` unlocks the next blob
  (invariant 6); `extra_questions` never do, regardless of whether
  they're answered, skipped, or ignored entirely. Graded through
  `/api/extra-submit`/`/api/extra-skip` and `apply_extra_question_result()`,
  which applies an intentionally asymmetric consequence, mirroring the
  synthesis-challenge precedent (`nudge_review_date`) but with a third,
  softer rung: correct is a no-op (not strong evidence of anything new),
  skipped is a *soft* nudge (pulls the blob's next review closer by half
  an interval - skipping carries no information about *what* is weak,
  just that it wasn't engaged with), incorrect is a *hard* nudge (forces
  the review immediately due, same as a synthesis miss) **and** records
  what was missed into that blob's `extra_gaps`.
- **`extra_gaps` feeds forward into later spaced-review variants and
  synthesis challenges, not just into timing.** `build_variant_prompt`/
  `build_synthesis_prompt` now accept the relevant blob(s)' `extra_gaps`
  and explicitly ask the generated exercise to re-probe that specific
  gap - this was the actual point of the feature, not a byproduct: an
  optional extra question isn't just "more practice," a wrong answer on
  one should shape what gets asked later, not just when. Verified live
  against a real `claude` call: a wrong answer conflating "worst-case
  complexity" with "how fast the computer is" produced a recorded gap,
  and the next generated review variant explicitly required identifying
  the worst case "in terms of how many elements must be checked, not
  how fast any computer runs" - the model actually used the gap, not
  just accepted the parameter. `extra_gaps` is cleared on the next
  *successful* review pass for that blob (`/api/review-submit`) - a
  clean pass is direct evidence the gap may no longer exist, so it
  shouldn't keep steering future generation at something resolved.
  Capped at the 3 most recent notes per blob so the prompt this feeds
  into doesn't grow unbounded over repeated attempts.
- **`nudge_review_date()` generalizes what was `apply_synthesis_result()`**
  - same "hard" (immediately due) behavior for a synthesis miss as
  before, plus the new "soft" (half-interval) severity for an extra
  question skip. One shared function rather than two similar ones,
  since both are instances of the same idea: an optional, non-gating
  signal that should influence spaced review without moving the
  Leitner box the way a direct primary-exercise miss does.

## Dev workflow

Run `scripts/test_engine.sh` after touching `server.py` before
committing — it spins up the engine against `example_content.json`,
exercises every endpoint (gating, submit pass/fail, locked-blob
rejection, hints, graph traversal, self-assessment, static serving),
asserts the responses, and tears itself down:

```bash
scripts/test_engine.sh
```

`scripts/check_dependencies.py` (Phase 0 of `SKILL.md`) can be run
standalone too - `python3 scripts/check_dependencies.py` - useful when
touching its tool list or hint text without running the whole skill.
Its Windows branch (and `venv_python()`'s) can only be verified by
logic/read-through in this environment - there's no Windows machine
here to actually run either against.

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

Three more, self-authored, exercise `convert_pdf.py` specifically —
epub's demos don't touch any of PDF's failure modes at all, so these
exist to isolate them one at a time:

```bash
python3 scripts/convert_pdf.py demo/pdf-demo-book.pdf /tmp/demo-pdf-out
python3 scripts/convert_pdf.py demo/pdf-no-outline-demo-book.pdf /tmp/demo-pdf-out-2
python3 scripts/convert_pdf.py demo/pdf-math-demo-book.pdf /tmp/demo-pdf-out-3
```

`demo/pdf-demo-book.pdf` (~28KB, 3 chapters/1 image) has a real
outline/bookmarks set via `doc.set_toc()` — the happy path. Checks
outline-based chapter splitting, image extraction, and running
header/footer stripping (`manifest.json` should report
`"chapter_confidence": "outline"`).

`demo/pdf-no-outline-demo-book.pdf` (~4KB, 2 chapters) deliberately has
no outline at all (`doc.set_toc()` is never called), forcing the
font-size/pattern heuristic fallback. Checks that `chapter_confidence`
correctly comes back `"heuristic"` and that the two large-font heading
lines are actually found as chapter starts.

`demo/pdf-math-demo-book.pdf` (~8KB, 1 chapter) has one equation set in
a font renamed to a known math-font name via `fontTools` (see the
design-decisions note on this above) — checks that the math span gets
rasterized into `media/` with a `[MATH: ...]` placeholder left in its
place, instead of extracted as garbled text.

None of the six demos' generated `content.json` is committed here
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
FUTURE_WORK.md                    open ideas / possible future work, not yet committed to
LICENSE                           MIT
scripts/check_dependencies.py     Phase 0 preflight - checks pandoc/node/claude, never installs
scripts/convert_epub.py           epub -> markdown + media (spine order, pandoc)
scripts/convert_pdf.py            PDF -> markdown + media (inferred structure, math as images, pymupdf)
scripts/test_engine.sh            automated regression check for server.py
demo/tiny-demo-book.epub          tiny self-authored PD epub, for pipeline sanity checks
demo/number-theory-demo-book.epub bigger self-authored PD epub (math+code), for generation/feature testing
demo/linear-algebra-demo-book.epub biggest demo, real embedded MathML, for testing math rendering
demo/pdf-demo-book.pdf            self-authored PD PDF w/ real outline+image, PDF happy-path testing
demo/pdf-no-outline-demo-book.pdf self-authored PD PDF w/ no outline, tests the heuristic chapter split
demo/pdf-math-demo-book.pdf       self-authored PD PDF w/ one math region, tests math font-detection
app-engine/server.py              generic server: content, submit, hint, review, graph, progress
app-engine/static/                generic frontend (index.html, app.js, style.css)
app-engine/static/vendor/katex/   vendored KaTeX (math rendering), not a CDN
app-engine/content/SCHEMA.md      content.json spec
app-engine/content/example_content.json   worked 3-blob example (used by test_engine.sh)
```
