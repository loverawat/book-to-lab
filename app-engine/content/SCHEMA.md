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
          "reading_html": "Optional pre-rendered HTML version of `reading`. If absent, the frontend wraps `reading` in a <p>.",
          "prerequisites": ["ch00-b03"],  // ids of blobs you should understand first (drives the knowledge graph)

          "exercise": {
            "type": "implementation",      // or "short_answer"

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

            // --- short_answer exercises (used only when a concept has no
            // natural implementation - e.g. a design tradeoff) ---
            "expected_answer": "The reference answer, shown after you self-assess."
          }
        }
      ]
    }
  ]
}
```

## Rules for the generation step (see ../../SKILL.md)

- `reading` and every exercise must be grounded in the chapter's own text -
  no outside knowledge, no generic best-practices that aren't in the book.
- Default `exercise.type` is `"implementation"`. Use `"short_answer"` only
  when forcing code would be artificial busywork (e.g. a pure tradeoff
  discussion) - and even then prefer an applied, scenario-based question
  over pure recall.
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
