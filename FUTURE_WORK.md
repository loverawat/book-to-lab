# FUTURE_WORK.md

Ideas and open questions for this repo, captured so they don't get lost
or re-discovered from scratch in a future session. These are **not
commitments** — evaluate each when there's a concrete reason to (a book
that actually needs it, a session with time to spend), not on a
schedule. If you pick one up, do the work as a real commit/PR and then
remove or update its entry here — don't leave a half-implemented version
sitting alongside its own TODO.

## Implementation exercises are narrower than they need to be

`test_code`/`starter_code`/`reference_solution` being written "in
Python" doesn't require the *skill being tested* to be Python —
`test_code` is just a harness and can shell out, use `sqlite3` (stdlib)
to check a SQL query, use `re` to validate a regex, write/read a config
file and assert on it, etc. Right now `SKILL.md` defaults every
implementation exercise to literal Python code regardless of what the
book actually teaches (see the linear algebra demo generating 8/8
"implement a function" exercises — CLAUDE.md's design-decisions note on
`short_answer` eligibility covers the fix already made for the
interpretation-vs-computation half of this). Using Python purely as an
execution harness for a non-Python skill needs no engine change, just
generation guidance in `SKILL.md` recognizing when the book's actual
skill isn't "write Python."

Separately, there's a real schema gap: exercises whose correct artifact
is inherently non-executable (a system design, a schema/architecture
decision, a diagram, a written spec) have no home except `short_answer`,
which frames everything as "explain in prose" rather than "produce this
concrete thing and get graded on whether it's right." Closing that would
mean either a third exercise type (claude-graded, "build X" framing
instead of "explain X") or loosening `short_answer` to explicitly cover
"produce an artifact" prompts. Only worth doing once we hit concrete
cases the Python-harness trick genuinely can't cover — try that first.

The core reframe worth keeping: "implementation" really means "produce
a concrete artifact by applying the concept," and code is just the
special case where that artifact happens to be executable. Dropping
"executable" as a requirement opens up categories that today have no
real home (they'd all currently default to `short_answer`-as-prose, or
get force-fit into Python code that doesn't test what matters):

- **Manual worked derivation** — actually carrying out the procedure by
  hand (solve the equation, compute the statistic from given data, work
  the accounting entry, derive the proof step) rather than writing code
  that does it. Pedagogically different from coding it: code can hide a
  misunderstanding behind logic copied from a hint, typing out each step
  directly exercises procedural fluency. Deterministically gradeable if
  the final answer is a specific number/expression; claude-graded if
  partial credit for the steps themselves matters.
- **Structured design artifacts** — a schema, an ER diagram, a system
  architecture sketch (Mermaid/ASCII), a component-responsibility list,
  a DDL statement. The book taught a design principle; the exercise is
  "design something using it," not "explain the principle." Natural for
  systems-design/database/architecture books. Claude-graded against the
  book's own stated criteria for a good design, same grounding rule as
  everything else.
- **Applied writing** — a paragraph, email, or argument that actually
  applies the specific technique just taught, not "explain the
  technique." Natural for rhetoric/communication/writing books, which
  today have no implementation story at all (no code to write) - every
  concept in that kind of book currently defaults to
  `short_answer`-as-explanation, missing "learn by doing" for that whole
  genre.
- **Declarative/configuration artifacts** — a regex, a config file, a
  query. Overlaps with the Python-harness idea above, but the
  distinction matters: here the artifact itself (the regex, the SQL) is
  what's being taught, and Python is only ever the test harness around
  it, never something the learner is being taught.
- **Case-based application** — given a new scenario, apply the book's
  framework and produce a decision/plan with justification, not just
  describe the framework. Natural for strategy/negotiation/ethics/law
  books - this is where "implementation" for a non-technical book most
  naturally lives, since these books are inherently about applying a
  framework to situations, not computing anything.
- **Constructed formal objects** — a proof, a syllogism, a truth table,
  a labeled fallacy in a passage. Natural for logic/philosophy/discrete-
  math books - checkable structure, but not runnable code.

The categories above are all "build it from scratch." A second set
tests a different cognitive mode - repair, translation, judgment - which
is often more diagnostic than fresh production, since a learner can
sometimes produce a correct-looking artifact by pattern-matching the
book's own example without actually understanding why it's correct:

- **Critique/repair** — give a flawed artifact (a buggy-but-non-code
  design, a broken argument, a proof with a subtle gap, a poorly
  structured plan) and have the learner find and fix what's wrong.
  Repairing a specific flaw requires knowing what it violates in a way
  that producing a correct-looking artifact from scratch doesn't always
  require. Applies anywhere "structured design artifacts" or
  "constructed formal objects" above apply.
- **Representation translation** — convert the concept from the
  modality it was taught in into a different one: a word problem into
  an equation, a state machine into a table, prose into a flowchart, a
  formal proof into plain English (or the reverse). The dual-coding
  technique from learning science - rote copying doesn't survive a
  change of representation, so it's a strong test that the underlying
  model actually transferred, not just the surface form.
- **Construct the counterexample, not the solution** — instead of
  solving a problem, construct an input that breaks a given claim, or a
  case where a property fails ("give an input where this algorithm gets
  the wrong answer," "construct a case with zero determinant that isn't
  obviously singular," "write a sentence committing this specific
  fallacy"). Flips the usual direction and tests understanding of a
  concept's *boundaries*, not just its typical case - often catches
  shallow understanding a normal solve-it exercise wouldn't.
- **Predict, then verify** — state a prediction (a sign, an order of
  magnitude, which of two outcomes) before doing the derivation/
  calculation, then reveal the actual result and compare. Standard
  technique in physics/stats teaching for surfacing misconceptions
  before they get papered over by the correct answer. Pairs naturally as
  a two-part exercise on one blob - a concrete use case for "Authored
  multi-question blobs" below.
- **Ordering/sequencing** — given shuffled steps of a process (algorithm
  steps, a causal chain, order of operations), reconstruct the correct
  order and justify the dependency. Cheap to grade (compare the
  sequence), and directly probes whether the learner understands *why*
  each step depends on the one before - which is also exactly what the
  prerequisite knowledge graph (see "Knowledge graph depth" below)
  already encodes per blob. The graph could plausibly double as source
  material for generating this exercise type, not just stay a read-only
  browsing aid.
- **Rank/compare candidates** — given two or three candidate solutions
  to the same problem, rank them or pick the better one using the
  book's own stated criteria, and justify why. Tests evaluative judgment
  rather than production - a good fit where the book's actual point is
  "here's what separates good from bad" rather than a procedure to
  execute (design/writing/strategy books again).

- **Where it genuinely can't go further** — books whose "hands-on" is
  physically real (cooking, a craft, a workout) have no digital
  verification path at all, code or otherwise. The honest move there
  isn't inventing a fake grading mechanism, it's the same self-report
  fallback `short_answer` already has ("I did it" / "I didn't") - a
  legitimate exercise type for that case, not a gap to engineer around.

None of this needs a new grading *mechanism* - deterministic where a
harness can check it (derivations with a specific answer, config/query
artifacts, an ordering task's exact sequence), claude-graded against
book criteria otherwise (designs, applied writing, case decisions,
proofs, repairs, translations, counterexamples, rankings), self-report
where nothing else is possible (physical actions). What's actually new
is the *prompt framing* recognizing "produce, repair, translate, or
judge an artifact" as its own category, distinct from both "write
runnable code" and "explain in prose" - which is exactly the
third-type/loosened-`short_answer` gap described above.

**Tradeoff to weigh before going further:** going beyond "shell out from
Python" — adding real first-class support for other languages (Rust,
Go, actual `.sql` files, etc.) via new `RUNNERS` entries in `server.py`
— pulls against invariant 4 (zero required setup beyond pandoc +
python3). JS support already made this tradeoff once (assumes `node` is
on PATH), so there's precedent, but each new language is a toolchain
assumption the user might not have, discovered only when they hit a
book that needs it.

## Authored multi-question blobs

Each blob currently has exactly one authored exercise in `content.json`.
Runtime-generated extras (spaced review, synthesis) are now surfaced
inline between blobs (see CLAUDE.md's design-decisions section), but
those are ephemeral and progress-dependent by design — they can't be
authored at generation time. A different idea: let generation itself
author 2-3 questions per blob (e.g. one implementation + one short
conceptual check), stored in `content.json`. Would need: a schema change
(`blob.exercise` → a list), a decision on what "passing" a blob means
with multiple questions (current lean: only the primary one gates
progression, extras are supplementary — matches invariant 6, "only the
primary exercise gates"), and `SKILL.md` guidance for when a second
authored question earns its place versus just adding busywork.

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
