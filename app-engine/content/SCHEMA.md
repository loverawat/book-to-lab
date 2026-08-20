# content.json schema

This is the one file that makes the generic app engine specific to a book.
The skill generates this file from the converted markdown; the engine
(`server.py` + `static/`) never changes per book.

```jsonc
{
  "title": "Book Title",
  "language": "python",           // "python" | "javascript" - drives which
                                    // interpreter runs implementation exercises
  "dependencies": ["numpy"],      // third-party packages (Python: pip names,
                                    // optionally pinned, e.g. "requests==2.31.0")
                                    // this book's exercises import beyond the
                                    // standard library. [] or omitted if none -
                                    // only used when language is "python"; see
                                    // "Per-book dependency isolation" below.
  "chapters": [
    {
      "id": "ch01",
      "title": "Chapter 1: Human-readable title",
      "blobs": [
        {
          "id": "ch01-b01",        // must be globally unique, stable, referenced by prerequisites
          "concept": "Short concept name (shown in sidebar)",
          "reading": "Markdown/plain text excerpt explaining the concept, grounded in the book's own words.",
          "reading_html": "Optional pre-rendered HTML version of `reading`. If absent, the frontend wraps `reading` in a <p>. Can include <img src=\"media/<file>\"> for a book image relevant to this concept - see \"Referencing book images\" below.",
          "prerequisites": ["ch00-b03"],  // ids of blobs you should understand first (drives the knowledge graph)

          "exercise": {
            "type": "implementation",      // or "short_answer" or "artifact"

            // --- implementation exercises ---
            "prompt": "What to build.",
            "starter_code": "def solve(...):\n    ...\n",
            "test_code": "from solution import solve\nassert solve(2) == 4\nprint('ok')",
            "hints": [
              "Gentle nudge - what pattern applies here?",
              "More specific - name the function/technique to use.",
              "Near-solution - describe the exact steps."
            ],
            "reference_solution": "def solve(...):\n    return ...\n",

            // --- short_answer exercises (a discrete question with one
            // right answer/explanation - used when forcing code would be
            // artificial busywork, e.g. a pure design tradeoff) ---
            "expected_answer": "The reference answer, shown after you self-assess.",

            // --- artifact exercises (produce/repair/translate/judge a
            // concrete but non-executable artifact - see SKILL.md's
            // "Decide exercise type per blob" for the full criteria) ---
            "reference_artifact": "The reference artifact/rubric, shown after you self-assess."
          },

          // Optional, 0-2 entries. Same shape as `exercise` (each is its
          // own {type, prompt, ...} object), but these never gate
          // progression - only `exercise` does. Offered inline once
          // `exercise` is passed. See "Extra (optional) questions" below.
          "extra_questions": [
            { "type": "implementation", "prompt": "...", "starter_code": "...", "test_code": "...", "hints": [], "reference_solution": "..." }
          ]
        }
      ]
    }
  ]
}
```

## Rules for the generation step (see ../../SKILL.md)

- `reading` and every exercise must be grounded in the chapter's own text -
  no outside knowledge, no generic best-practices that aren't in the book.
- Default `exercise.type` is `"implementation"` - but that includes using
  the book's detected language purely as a *harness* around a non-code
  skill (a query, a regex, a config file) when that's what the book is
  actually teaching, not literally writing idiomatic code in that
  language for its own sake. Use `"short_answer"` for a discrete
  question with one right answer/explanation when forcing code would be
  artificial busywork. Use `"artifact"` when the concept's point is
  producing, repairing, translating, or judging a concrete but
  inherently non-executable thing (a design, a proof, applied writing,
  a critique) - see SKILL.md's "Decide exercise type per blob" for the
  full three-way decision and a taxonomy of `artifact` categories.
  `short_answer` and `artifact` are graded the same way
  (`build_grading_prompt`, claude-graded with a self-assess fallback);
  the difference is prompt framing (explain X vs. produce/repair/
  translate/judge X) and which reference field they use
  (`expected_answer` vs. `reference_artifact` - see
  `exercise_reference_text()` in `server.py`).
- `test_code` must be self-contained: it imports from `solution.<ext>`
  (the file the learner's submission is written to) and exits non-zero on
  failure. No network calls. Prefer hardcoded input/output pairs for
  simple exercises, but where it's natural, generate random valid inputs
  seeded from the `BOOK_TO_LAB_SEED` environment variable (a fresh value
  every run, set by the engine) and check correctness against a property
  or a small reference implementation embedded in the test itself, rather
  than one fixed input/output pair - this stops a submission from passing
  by matching memorized specific values instead of actually solving the
  general problem. Only do this where a real independent check is
  possible (a property that must hold, or a reference computation using a
  different method than the one being tested) - don't fake determinism
  with a check that's really just re-deriving the same fixed answer.
- `prerequisites` should point to blob ids introduced earlier in the book
  (usually, but not always, the immediately preceding blob). This is what
  powers the "prerequisites for this concept" graph, traversed 3-4 levels
  deep.
- Blob order in `chapters[].blobs[]` is the linear gating order: a blob
  only unlocks once the previous one is passed.

## Referencing book images

`convert_epub.py`/`convert_pdf.py` extract every book image into
`<output_dir>/media/`, outside `app/` - the engine never serves that
directory directly. To actually show one of these images in the app,
the generation step must copy the specific file into
`<output_dir>/app/static/media/` (created the first time it's needed)
and reference it from `reading_html` as `<img src="media/<file>"
alt="...">`. `server.py`'s static handler already serves anything under
`app/static/`, so this needs no engine change - just the file being
where it's reachable. Only copy images actually relevant to that blob's
concept, not every image that happened to be nearby in the source; see
`SKILL.md`'s Phase 2 for the full guidance.

## Extra (optional) questions

`extra_questions` (0-2 per blob) let a blob carry supplementary
authored questions beyond its one primary `exercise` - same object
shape, graded through the same paths (`/api/extra-submit`,
`/api/extra-skip`). They are strictly non-gating: only `exercise`
determines whether the next blob unlocks, and this stays true
regardless of whether any `extra_questions` exist, get answered, or get
skipped. The frontend only offers them once `exercise` is already
passed.

They're not consequence-free, though - correctness has an asymmetric
effect on this blob's own spaced review (`apply_extra_question_result`
in `server.py`), never on its Leitner box (only a miss on the *primary*
exercise moves that):
- **Correct** - no effect. Not strong enough evidence to change
  anything already established by passing the primary.
- **Skipped** - a soft nudge: pulls the blob's next review date closer
  by half an interval. Skipping says nothing about *what* is weak, just
  that it wasn't engaged with.
- **Incorrect** - a hard nudge: forces the blob's next review
  immediately due, *and* records what was missed (the grading
  feedback, for `short_answer`; a short descriptor for
  `implementation`) into that blob's `extra_gaps`. The next spaced-
  review variant or synthesis challenge involving this blob reads
  `extra_gaps` and is specifically asked to re-probe that gap, not just
  generically retest the concept (see `build_variant_prompt`/
  `build_synthesis_prompt`). A later successful review pass clears
  `extra_gaps` - direct evidence the gap may be resolved.

Not every blob needs `extra_questions`; most shouldn't have any. See
`SKILL.md`'s Phase 2 for when a second authored question earns its
place versus just adding busywork.

## Per-book dependency isolation

If any exercise's `test_code`/`starter_code`/`reference_solution` imports
a third-party package, list it in the top-level `dependencies` array.
On first run, `server.py` creates a venv at `<app_dir>/.venv` containing
exactly those packages and runs all of that book's implementation
exercises through it - never the system Python, and never shared with
any other book. Leave `dependencies` empty (or omit it) for books that
only need the standard library; no venv is created in that case, so
there's zero setup cost. Keep the list minimal - only what the
exercises actually import, not everything the book happens to mention.
