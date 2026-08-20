# FUTURE_WORK.md

Ideas and open questions for this repo, captured so they don't get lost
or re-discovered from scratch in a future session. These are **not
commitments** — evaluate each when there's a concrete reason to (a book
that actually needs it, a session with time to spend), not on a
schedule. If you pick one up, do the work as a real commit/PR and then
remove or update its entry here — don't leave a half-implemented version
sitting alongside its own TODO.

## Implementation exercises are narrower than they need to be — done

`SKILL.md`'s "Decide exercise type per blob" is now a genuine three-way
decision - `implementation` (default, including using the book's
detected language purely as a *harness* around a non-Python/JS skill -
a SQL query checked via `sqlite3`, a regex checked via `re`, when
that's what the book is actually teaching), `short_answer` (a discrete
question with one right explanation), and new **`artifact`** (produce/
repair/translate/judge a concrete but inherently non-executable thing).
`artifact` reuses `short_answer`'s exact grading mechanism
(`build_grading_prompt`, self-assess fallback, `/api/grade-answer`) via
a new `exercise_reference_text()` helper that reads `reference_artifact`
instead of `expected_answer` - zero new grading machinery, only prompt
framing and one field name differ. Threaded through every claude-graded
path: grading, review variants, synthesis challenges, extra questions.
Full taxonomy (manual derivation, structured design, applied writing,
critique/repair, representation translation, counterexample
construction, predict-then-verify, ordering, rank/compare, and the
honest physical-action boundary) lives in `SKILL.md` itself now, not
just here - see "Decide exercise type per blob".

**Verified two ways, not just written:**
- Every claude-graded endpoint tested live against real `claude` calls
  with `artifact`-type content: correct/incorrect grading, review-variant
  generation (correctly produced a fresh scenario with `reference_artifact`
  in the right shape), self-assess/reveal wording.
- A real trial generation pass against `demo/linear-algebra-demo-book.epub`
  - the same book that originally exposed the "8/8 implementation"
  problem (see `CLAUDE.md`) - re-authored chapter by chapter under the
  new three-way guidance, at the same blob granularity as the original.
  Result: **4 implementation / 3 artifact / 1 short_answer** across 8
  blobs (plus 2 typed `extra_questions`), not 8/8. Concrete examples
  that actually landed: the vector-magnitude section as a manual
  derivation (artifact), the determinant section as predict-then-verify
  (artifact), the matrix-form-of-a-system section as representation
  translation (artifact), an `AB ≠ BA` counterexample-construction as an
  extra question. Every `test_code`/`reference_solution` pair was
  executed and passed; every `short_answer`/`artifact` reference was
  graded "correct" against itself; genuinely fresh wrong/right answers
  (not copied from the reference) were submitted against two extra
  questions and graded with specific, accurate feedback - including
  correctly catching a subtly-wrong counterexample (the identity matrix,
  which trivially commutes, missing the point of the exercise).

**Still explicitly out of scope, by choice this round:** real
first-class multi-language exercise runners (Rust, Go, actual `.sql`
files) via new `RUNNERS` entries in `server.py` - that pulls against
invariant 4 (zero required setup beyond pandoc + python3) and was kept
as a separate, bigger tradeoff rather than bundled into this pass. JS
support already made this tradeoff once (assumes `node` is on PATH), so
there's precedent, but each new language is a toolchain assumption the
user might not have, discovered only when they hit a book that needs
it.

## Authored multi-question blobs — done

`content.json` blobs can now carry 0-2 `extra_questions` alongside the
one primary `exercise` — same object shape, authored the same way.
Strictly non-gating: only `exercise` unlocks the next blob, exactly as
before; `extra_questions` never do. Offered inline once the primary is
passed, graded through new `/api/extra-submit`/`/api/extra-skip`
endpoints (both server-side gated on the primary already being
`"passed"`, per invariant 6). See `CLAUDE.md`'s design-decisions
entries and "Extra (optional) questions" in
`app-engine/content/SCHEMA.md` for the full mechanism.

The consequence model landed as three rungs, not two: correct is a
no-op; skipped is a *soft* nudge (pulls the blob's next review closer
by half an interval - skipping carries no signal about what's weak,
just that it wasn't engaged with); incorrect is a *hard* nudge (forces
the review immediately due) **and** records what was missed into that
blob's `extra_gaps`, which `build_variant_prompt`/`build_synthesis_prompt`
now read so a later review variant or synthesis challenge involving
that blob specifically re-probes the identified gap, not just
generically retests the concept. Cleared on the next successful review
pass. `nudge_review_date()` (generalized from what was
`apply_synthesis_result()`) is the shared mechanism behind both the
soft and hard severities, and now also behind synthesis-challenge
misses, which previously only had the hard case.

Verified end-to-end against a real content pack, not just written: the
full gating chain (locked → primary-not-passed → correct → incorrect →
skip → invalid index), the box-never-moves/last_reviewed-changes
distinction, and - the actual point of the feature - a live `claude`
call confirmed a recorded gap (conflating "worst-case complexity" with
"how fast the computer is") produced a generated review variant that
explicitly re-probed that exact misconception, not a generic variant.
`test_engine.sh` covers the deterministic (implementation-type)
gating/status/nudge paths (33 checks now); the claude-graded
short-answer path and the gap-injection-into-generation path were
verified manually against a live `claude` CLI call, same category as
every other claude-dependent path in this engine.

## Knowledge graph depth — verified, not a gap

Confirmed: checked on a concept several chapters into a book, and the
prerequisite graph correctly shows multiple levels, not just 1. The
earlier depth-1 observation was exactly what was already suspected - an
early blob legitimately has few or no prerequisites, not a bug in
`build_graph`/`expand` in `server.py`. No code change needed.

## Extracted book images are never actually shown (dead `media/`) — done

`SKILL.md`'s Phase 2 now copies specific, relevant images from
`<output_dir>/media/` into `<output_dir>/app/static/media/` and
references them from `reading_html` as `<img src="media/<file>">` - see
`CLAUDE.md`'s "Book images are copied into `app/static/media/`" note
and "Referencing book images" in `app-engine/content/SCHEMA.md`. No
engine change was needed beyond fixing `server.py`'s static handler to
send the correct `Content-Type` for image extensions (it previously
fell back to `application/octet-stream` for everything but
html/js/css/json - browsers render `<img>` fine regardless via
content-sniffing, but this was worth fixing properly once image serving
became a real, deliberate capability rather than an incidental one).
Verified end-to-end against a real extracted image (from
`demo/tiny-demo-book.epub`): copied into a scratch app's
`static/media/`, served via HTTP with the right content-type, bytes
confirmed identical to the source file. `test_engine.sh` has a
regression check for this now too.

## Generated diagrams/animations per blob — done

`SKILL.md`'s Phase 2 now has explicit guidance for this, right after
the book-image-referencing paragraph: judgment-gated (not a per-blob
default), classifies a concept as static vs. process/transformation
before deciding whether a book image already covers it (static → book
image wins outright, generation is only a fallback; process → a still
image can't show the transformation regardless of whose image it is,
so an animation can be worth generating even when a relevant book image
already exists, and the two can coexist), defaults to hand-authored
inline SVG (+ CSS `@keyframes`), and only executes a script
(`matplotlib` + Pillow's `PillowWriter`, no `ffmpeg` needed) when
hand-computed coordinates would be genuinely error-prone. Script
execution reuses the *same* isolated skill-tooling venv `convert_pdf.py`
already created for `pymupdf` (`<skill_dir>/.venv`), not a separate one
- see `CLAUDE.md`'s design-decisions entries for the full reasoning.
Output is saved into `app/static/media/` and referenced exactly like a
book image - no schema change, no engine change.

Verified end-to-end, not just written: a hand-authored inline SVG (a
vector-addition animation using `<animate>`) confirmed well-formed XML
and round-trips through `/api/content` intact; a real `matplotlib`
script (a rotating vector via `FuncAnimation` + `PillowWriter`) was
actually run through the reused skill venv, produced a genuine 30-frame
GIF (verified frame-by-frame, one frame visually inspected), and served
correctly over HTTP with the right content-type. `test_engine.sh`'s
existing 25 checks still pass unchanged (no engine code was touched -
this feature needed none).

**Not verified:** a live Phase 2 generation session has never actually
exercised this guidance on a real book - whether a real generation
session correctly judges static-vs-process, correctly decides when a
book image is "enough" vs. when an animation adds real value, and
produces SVG/`matplotlib` output that's actually well-designed (not
just mechanically valid) is untested, same category of gap as the PDF
math-transcription instruction.

Manim (real math-animation quality) is still explicitly out of scope -
see "Relaxing invariant 4" below, unchanged.

## Grading only sees the current blob's reading, not its prerequisites

Raised in conversation: the app is architecturally a *replacement* for
reading the book, not a supplement - `build_grading_prompt`/
`build_variant_prompt`/`build_synthesis_prompt` all explicitly instruct
claude to judge/generate "ONLY against the book excerpt... no outside
knowledge" (invariant 2). That's enforced for the *learner* by gating -
by the time they reach blob N they've necessarily passed everything
before it - but not for the *grader*. `/api/grade-answer`,
`/api/review-submit`, `/api/extra-submit`, and `/api/review-due`'s
variant generation all currently ground on only the *current* blob's
own `reading`, not any prerequisite's - so if a good answer legitimately
needs something established in an earlier blob and never restated in
the current one, claude is grading with less context than the learner
actually has. `build_synthesis_prompt` already gets this right (it
explicitly combines multiple blobs' excerpts); the single-blob paths
don't.

**Design worked out, not yet built** (deliberately held back - "let me
experience it first, then decide whether to fix it"):

- New helper `prerequisite_excerpts(content, blob)` - `(concept,
  reading)` pairs for each of the blob's *direct* `prerequisites`, in
  order. Deliberately not the full transitive chain and not "every blob
  passed so far" (which gating would technically allow) - `prerequisites`
  is already curated, judgment-authored data (`SKILL.md`'s generation
  guidance already says to "reach further back when a concept genuinely
  depends on something from an earlier chapter"), so it's already the
  deliberate answer to "what does this concept actually depend on,"
  not just reading order. Reusing it is a natural fit; walking the full
  graph or dumping full history would dilute the "ground ONLY in the
  relevant excerpt" instruction with noise.
- `build_grading_prompt` and `build_variant_prompt` gain an optional
  `prerequisite_excerpts` parameter, rendered as a new section placed
  *before* the main excerpt (not merged into it) - background context,
  not competing with what's actually being tested. Ordering matters:
  keep the main excerpt closest to the actual task, prerequisite
  context further back, so it reads as "general background -> specific
  focus -> what to do," not two sources of equal weight.
- Four call sites updated: `/api/grade-answer`, `/api/review-submit`,
  `/api/extra-submit`, `/api/review-due`. All already load `content`, so
  it's just `prerequisite_excerpts(content, blob)` passed through.
- Deliberately out of scope: `build_synthesis_prompt` - already grounds
  in multiple blobs' excerpts at once (richer context than the paths
  that actually have the gap), and pulling in prerequisites-of-
  prerequisites across 2-3 combined blobs multiplies complexity for a
  case that isn't where the problem shows up. Treat as a separate call
  if it turns out to matter in practice.

**Known limitation of the design as scoped, not something it tries to
fix:** it passes each prerequisite's *entire* `reading`, not a
relevance-filtered excerpt - `prerequisites` is a list of blob ids, so
it's all-or-nothing at the blob level, not a pointer to a specific fact
within one. This mostly doesn't matter in practice *because* blobs are
already chunked to "roughly one idea per blob" (`SKILL.md`), so a
prerequisite's `reading` is already small and single-concept - there's
little to filter out. It would only bite if a specific prerequisite
blob is poorly chunked (genuinely covers more than one idea) - that's a
chunking-quality issue upstream, not something this fix should
compensate for with its own filtering layer (a second `claude` call to
pre-filter context, or asking the grading call to do double duty,
would add real latency/cost for a case that's rare if chunking is done
well).

## Relaxing invariant 4 (zero required setup beyond pandoc + python3)

**Done, not open anymore:** the preflight-check, guided-install, and
Windows-venv-bug pieces originally captured in this section are
implemented - see `scripts/check_dependencies.py` (Phase 0 of
`SKILL.md`), invariants 4 and 9 and the design-decisions note on the
checker's scope in `CLAUDE.md`, and the `venv_python()` fix in
`server.py`. What's genuinely still open is only the bigger question
below.

**Still open: what relaxing invariant 4 itself would unlock** — a couple
of ideas elsewhere in this file are still genuinely gated on this, and
neither is decided:
- Manim instead of matplotlib-only for the diagram/animation idea above
  — real math-animation quality, but needs ffmpeg + cairo + (optionally)
  a LaTeX distribution, none of which `pip`/`venv` alone can install.
- Real first-class multi-language exercise runners (Rust, Go, actual
  Postgres-flavor SQL, shell) — see the tradeoff note in "Implementation
  exercises are narrower than they need to be" above.

(PDF support's own conversion tooling turned out *not* to need this
after all — `pymupdf` is pure `pip`, so it got its own isolated
skill-tooling venv instead of requiring any invariant-4 relaxation; see
"PDF input support" below. OCR for scanned PDFs would likely follow the
same pattern if it's ever built, not a reason to relax invariant 4
either - it's simply not built, see that section's still-open list.)
- Always-available scientific stack (numpy/scipy/pandas/networkx)
  instead of per-book opt-in `dependencies`.

The cost isn't any one of these individually - it's that "just clone and
run" stops being literally true, and the README's pitch has to change
from "zero setup" to "here's what you need per feature." A deliberate
threshold decision to make once, not something to slide into one
feature at a time by relaxing it quietly for whichever one comes up
first.

## PDF input support (alongside epub, not replacing it)

**Done:** `scripts/convert_pdf.py` exists and produces the same
`markdown/`/`media/`/`manifest.json` shape as `convert_epub.py` — see
`CLAUDE.md`'s design-decisions entries (search "PDF") for the full
implementation: outline-first/heuristic-fallback/single-chapter chapter
splitting with a `chapter_confidence` flag, document-wide running
header/footer stripping, image extraction, and math detected by
embedded font name and rasterized to an image (transcribed to LaTeX by
the Phase 2 generation session reading that image directly, not by
automated OCR). Its own isolated venv (`<skill_dir>/.venv`) keeps
`pymupdf` out of both invariant 4's scope and any book's per-book venv.
Three self-authored demo PDFs (`demo/pdf-*.pdf`) exercise the happy
path, the no-outline heuristic fallback, and math detection
respectively. `SKILL.md` branches on input extension; `README.md` and
`CLAUDE.md` document the feature and its tradeoffs.

**Still genuinely open / not covered by the above:**

- **Multi-column layouts aren't specially handled.** Text extraction
  relies on `pymupdf`'s own block ordering, which is reasonable for
  standard single-column layouts but untested against a real multi-
  column academic paper/textbook layout — no such fixture exists yet.
  If a real book's columns come out interleaved wrong, this is where to
  look first.
- **The math-font heuristic has never been validated against a PDF
  LaTeX actually produced.** The demo fixture proves the detection code
  path works (a font named like a real math font gets flagged and
  rasterized), but it's a renamed-and-subsetted system font, not
  genuine Computer Modern/Latin Modern Math output from a real LaTeX
  toolchain — no LaTeX distribution was available in the environment
  this was built in. Worth a real test against an actual LaTeX-produced
  PDF before trusting this on a real math-heavy book.
- **Scanned/image-only PDFs (no text layer) are explicitly out of
  scope**, unchanged from the original analysis below — `convert_pdf.py`
  assumes a real text layer exists.
- **Footnotes aren't specially filtered** — they'll extract as regular
  body text interleaved wherever they sit on the page, unlike running
  headers/footers (which the boilerplate-repetition heuristic does
  catch) or math (font-detected). Not tested against a real footnote-
  heavy book.

**Original risk analysis, still accurate context for the items above:**
PDF is fixed-layout (glyphs positioned on a page), not a linear/
reflowable document the way epub's XHTML is — multi-column layouts,
footnotes, and page numbers all end up interleaved into the extracted
text stream in a way epub's structure mostly avoids by construction.
Math was the biggest risk of all: most PDFs have zero semantic markup
for equations (unlike epub, where CLAUDE.md documents at length that
real EPUB3 math ships as actual MathML pandoc recognizes as a Math AST
node) — full automated LaTeX reconstruction from rendered PDF math is
what commercial tools like Mathpix exist to solve, and was judged too
heavy a dependency to take on directly. The font-detection +
vision-transcription approach that got built instead sidesteps that by
using the already-present multimodal generation session rather than a
new OCR/ML system — see `CLAUDE.md` for why that's a materially
different (and cheaper) answer than it first looked.
