#!/usr/bin/env python3
"""
book-to-lab app engine.

Generic local server for a generated book-lab. Reads content/content.json
(produced by the skill for one specific book) and serves:
  - the static frontend
  - reading content + exercises
  - exercise submission -> runs automated tests in a subprocess
  - progressive hints
  - a prerequisite knowledge graph (traversed from content.json)
  - progress persistence (progress.json, Leitner-style spaced review)
  - optional grounded review via the `claude` CLI

Run with: python3 server.py [port]
The engine itself uses only the Python standard library - no pip
install required. If a book declares third-party dependencies (see
content.json's "dependencies" field), a venv for just that book is
created lazily on first run under <app_dir>/.venv, so those packages
never touch the system/global Python.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).parent.resolve()
STATIC_DIR = ROOT / "static"
CONTENT_PATH = ROOT / "content" / "content.json"
PROGRESS_PATH = ROOT / "content" / "progress.json"
VENV_DIR = ROOT / ".venv"

EXEC_TIMEOUT_SECS = 10


def venv_python():
    """Path to this book's isolated interpreter, if one has been set up."""
    candidate = VENV_DIR / "bin" / "python3"
    return str(candidate) if candidate.exists() else None


def ensure_venv(content):
    """Lazily create a per-book venv the first time a book declares
    third-party dependencies. No-op for books that only need the
    standard library, and no-op on every run after the first."""
    deps = content.get("dependencies", [])
    if not deps or VENV_DIR.exists():
        return
    print(f"Setting up an isolated environment for this book's dependencies ({', '.join(deps)})...")
    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
    pip = str(VENV_DIR / "bin" / "pip")
    subprocess.run([pip, "install", "--quiet", *deps], check=True)
    print("Done - this only happens once for this book.")


RUNNERS = {
    "python": {"ext": "py", "cmd": lambda path: [venv_python() or "python3", str(path)]},
    "javascript": {"ext": "js", "cmd": lambda path: ["node", str(path)]},
}


def load_content():
    return json.loads(CONTENT_PATH.read_text(encoding="utf-8"))


def load_progress():
    if PROGRESS_PATH.exists():
        return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    return {"blobs": {}, "current": None}


def save_progress(progress):
    PROGRESS_PATH.write_text(json.dumps(progress, indent=2), encoding="utf-8")


def _delayed_exit():
    time.sleep(0.3)
    os._exit(0)


def all_blobs(content):
    for chapter in content["chapters"]:
        for blob in chapter["blobs"]:
            yield chapter, blob


def find_blob(content, blob_id):
    for chapter, blob in all_blobs(content):
        if blob["id"] == blob_id:
            return chapter, blob
    return None, None


def ordered_blob_ids(content):
    return [blob["id"] for _, blob in all_blobs(content)]


def is_unlocked(content, progress, blob_id):
    order = ordered_blob_ids(content)
    idx = order.index(blob_id)
    if idx == 0:
        return True
    prev_id = order[idx - 1]
    return progress["blobs"].get(prev_id, {}).get("status") == "passed"


def run_code_test(language, submitted_code, test_code):
    runner = RUNNERS.get(language, RUNNERS["python"])
    ext = runner["ext"]
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        solution_file = tmp_path / f"solution.{ext}"
        test_file = tmp_path / f"test_solution.{ext}"
        solution_file.write_text(submitted_code, encoding="utf-8")
        test_file.write_text(test_code, encoding="utf-8")
        env = {**os.environ, "BOOK_TO_LAB_SEED": str(time.time_ns())}
        try:
            result = subprocess.run(
                runner["cmd"](test_file),
                cwd=tmp_path,
                capture_output=True,
                text=True,
                timeout=EXEC_TIMEOUT_SECS,
                env=env,
            )
            passed = result.returncode == 0
            output = (result.stdout or "") + (result.stderr or "")
        except subprocess.TimeoutExpired:
            passed = False
            output = f"Timed out after {EXEC_TIMEOUT_SECS}s (possible infinite loop)."
    return passed, output.strip()


def leitner_advance(box, passed, struggled=False):
    """struggled = it took more than one attempt to finally pass. A
    struggled pass still needs a near-term recheck rather than jumping
    straight into the normal box progression - getting it right on
    attempt 3 isn't the same evidence of retention as attempt 1."""
    if not passed:
        return 1
    if struggled:
        return 1
    return min(box + 1, 5)


def due_review_blob(content, progress):
    now = time.time()
    order = ordered_blob_ids(content)
    candidates = []
    for blob_id in order:
        state = progress["blobs"].get(blob_id, {})
        if state.get("status") != "passed":
            continue
        box = state.get("box", 1)
        last = state.get("last_reviewed", 0)
        interval_days = {1: 0.5, 2: 1, 3: 3, 4: 7, 5: 21}.get(box, 21)
        if now - last >= interval_days * 86400:
            candidates.append((last, blob_id))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]


def apply_synthesis_result(blob_ids, passed):
    """Synthesis questions are optional and never gate progress or move a
    blob's own Leitner box - failing to combine several concepts together
    is weaker evidence against any single one of them than missing a
    review question aimed directly at it. But it shouldn't be a no-op
    either: on failure, pull each component blob's next review forward to
    immediately due (last_reviewed reset, box left alone) so struggling to
    synthesize still feeds back into what gets resurfaced, just more
    gently than a direct miss (which resets the box too)."""
    if passed or not blob_ids:
        return
    progress = load_progress()
    changed = False
    for blob_id in blob_ids:
        state = progress["blobs"].get(blob_id)
        if state is not None:
            state["last_reviewed"] = 0
            changed = True
    if changed:
        save_progress(progress)


def recent_passed_blobs(content, progress, n=3):
    passed = [
        (progress["blobs"][bid].get("last_reviewed", 0), bid)
        for bid in ordered_blob_ids(content)
        if progress["blobs"].get(bid, {}).get("status") == "passed"
    ]
    passed.sort(reverse=True)
    return [bid for _, bid in passed[:n]]


def build_graph(content, blob_id, depth):
    _, target = find_blob(content, blob_id)
    if target is None:
        return None

    def expand(bid, remaining):
        _, blob = find_blob(content, bid)
        if blob is None:
            return {"id": bid, "concept": bid, "missing": True}
        node = {"id": bid, "concept": blob.get("concept", bid)}
        prereqs = blob.get("prerequisites", [])
        if remaining > 0 and prereqs:
            node["prerequisites"] = [expand(p, remaining - 1) for p in prereqs]
        elif prereqs:
            node["prerequisites"] = [{"id": p, "truncated": True} for p in prereqs]
        return node

    return expand(blob_id, depth)


def claude_review(book_title, excerpt, prompt, submission):
    review_prompt = textwrap.dedent(f"""
        You are grading a learning exercise for the book "{book_title}".
        Judge the learner's submission ONLY against the book excerpt below.
        Do not introduce outside best practices, libraries, or conventions
        that are not present in this excerpt. If the book's approach differs
        from general convention, the book's approach is correct here.

        --- BOOK EXCERPT (source of truth) ---
        {excerpt}
        --- END EXCERPT ---

        --- EXERCISE PROMPT ---
        {prompt}
        --- END EXERCISE PROMPT ---

        --- LEARNER SUBMISSION ---
        {submission}
        --- END SUBMISSION ---

        Give a short verdict (correct / partially correct / incorrect) relative
        to the excerpt, then 2-4 sentences of specific feedback. Be concise.
        If you use any math notation, write it as LaTeX with $...$ for inline
        or $$...$$ for display equations - it will be rendered, not other
        notation.
    """).strip()
    try:
        result = subprocess.run(
            ["claude", "-p", review_prompt],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return f"claude CLI error: {result.stderr.strip()}"
        return result.stdout.strip()
    except FileNotFoundError:
        return "claude CLI not found on PATH - install/login Claude Code to enable reviews."
    except subprocess.TimeoutExpired:
        return "claude CLI review timed out."


# --- structured (JSON-returning) claude CLI calls, used for grading with a
# verdict, generating spaced-review variants, and generating synthesis
# challenges. All grounded strictly in book excerpts, same rule as
# claude_review() above - see CLAUDE.md's design-decisions note on this.

def _extract_json_object(text):
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def call_claude_json(prompt, timeout=120):
    """Returns (parsed_dict, None) on success, or (None, error_message)."""
    try:
        result = subprocess.run(["claude", "-p", prompt], capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return None, "claude CLI not found on PATH."
    except subprocess.TimeoutExpired:
        return None, "claude CLI timed out."
    if result.returncode != 0:
        return None, f"claude CLI error: {result.stderr.strip()}"
    parsed = _extract_json_object(result.stdout)
    if parsed is None:
        return None, "Could not parse claude's response as JSON."
    return parsed, None


def build_grading_prompt(book_title, excerpt, exercise_prompt, expected_answer, answer,
                          follow_up_question=None, follow_up_answer=None):
    base = textwrap.dedent(f"""
        You are grading a learner's answer for the book "{book_title}".
        Judge ONLY against the book excerpt below - no outside knowledge or
        general best practices beyond what this excerpt says. If the book's
        view differs from common convention, the book's view is correct here.

        --- BOOK EXCERPT (source of truth) ---
        {excerpt}
        --- END EXCERPT ---

        --- QUESTION ---
        {exercise_prompt}
        --- END QUESTION ---

        --- REFERENCE ANSWER (for your grounding only; the learner never sees this wording) ---
        {expected_answer}
        --- END REFERENCE ANSWER ---

        --- LEARNER'S ANSWER ---
        {answer}
        --- END LEARNER'S ANSWER ---
    """).strip()

    if follow_up_question is not None:
        base += "\n\n" + textwrap.dedent(f"""
            --- FOLLOW-UP QUESTION YOU ASKED ---
            {follow_up_question}
            --- END FOLLOW-UP QUESTION ---

            --- LEARNER'S FOLLOW-UP ANSWER ---
            {follow_up_answer}
            --- END FOLLOW-UP ANSWER ---

            This is the second and final round - do not ask another follow-up.
            If you use math notation anywhere below, write it as LaTeX with
            $...$ inline or $$...$$ for display equations - it will be
            rendered, not other notation.
            Respond with ONLY a JSON object, no other text, no markdown fences:
            {{"verdict": "correct" or "incorrect", "feedback": "2-4 sentences of specific feedback"}}
        """).strip()
    else:
        base += "\n\n" + textwrap.dedent("""
            If you use math notation anywhere below, write it as LaTeX with
            $...$ inline or $$...$$ for display equations - it will be
            rendered, not other notation.
            Respond with ONLY a JSON object, no other text, no markdown fences:
            {"verdict": "correct" or "partial" or "incorrect",
             "feedback": "2-4 sentences of specific feedback",
             "follow_up_question": "a targeted question probing exactly the gap, or null if verdict is correct"}
        """).strip()
    return base


def build_variant_prompt(book_title, blob, language):
    exercise = blob["exercise"]
    shape = (
        '{"prompt": "...", "starter_code": "...", "test_code": "...", "reference_solution": "..."}'
        if exercise["type"] == "implementation"
        else '{"prompt": "...", "expected_answer": "..."}'
    )
    return textwrap.dedent(f"""
        You are writing a FRESH variant of an existing exercise, for spaced
        review, testing the same concept from the book "{book_title}" but
        with different specifics (different inputs/scenario) so it can't be
        passed just from memory of the original. Ground it ONLY in this
        excerpt - no outside knowledge or conventions beyond what's here.

        --- EXCERPT ---
        {blob.get("reading", "")}
        --- END EXCERPT ---

        --- ORIGINAL EXERCISE (format/style reference only - don't reuse its specifics) ---
        {json.dumps(exercise)}
        --- END ORIGINAL ---

        Language for any code: {language}.
        If you use math notation in the prompt or answer, write it as LaTeX
        with $...$ inline or $$...$$ for display equations - it will be
        rendered, not other notation.
        Respond with ONLY a JSON object, no other text, no markdown fences:
        {shape}
    """).strip()


def build_synthesis_prompt(book_title, blob_excerpts, language):
    joined = "\n\n".join(f"[{concept}]\n{text}" for concept, text in blob_excerpts)
    return textwrap.dedent(f"""
        You are creating a synthesis exercise for the book "{book_title}"
        that requires combining ALL of the concepts below together in one
        exercise - not testing them separately. Ground it ONLY in these
        excerpts - no outside knowledge or conventions beyond what's here.

        {joined}

        Language for any code: {language}.
        If you use math notation in the prompt or answer, write it as LaTeX
        with $...$ inline or $$...$$ for display equations - it will be
        rendered, not other notation.
        Respond with ONLY a JSON object, no other text, no markdown fences:
        {{"type": "implementation" or "short_answer",
          "prompt": "what to build/answer, requiring combining these concepts together",
          "starter_code": "stub - only if type is implementation",
          "test_code": "self-contained test importing from solution.<ext> - only if type is implementation",
          "reference_solution": "only if type is implementation",
          "expected_answer": "only if type is short_answer"}}
    """).strip()


REVIEW_VARIANTS = {}       # blob_id -> ephemeral variant exercise dict
SYNTHESIS_CHALLENGES = {}  # challenge_id -> ephemeral challenge dict


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw or b"{}")

    def do_GET(self):
        parsed = urlparse(self.path)
        path, query = parsed.path, parse_qs(parsed.query)

        if path == "/api/content":
            content = load_content()
            progress = load_progress()
            order = ordered_blob_ids(content)
            for blob_id in order:
                progress["blobs"].setdefault(blob_id, {"status": "locked", "box": 1, "last_reviewed": 0})
                if is_unlocked(content, progress, blob_id) and progress["blobs"][blob_id]["status"] == "locked":
                    progress["blobs"][blob_id]["status"] = "available"
            save_progress(progress)
            self._json({"content": content, "progress": progress})
            return

        if path == "/api/review-due":
            content = load_content()
            progress = load_progress()
            blob_id = due_review_blob(content, progress)
            if blob_id is None:
                self._json({"blob": None})
                return
            _, blob = find_blob(content, blob_id)

            variant_prompt = build_variant_prompt(
                content.get("title", "this book"), blob, content.get("language", "python")
            )
            variant, error = call_claude_json(variant_prompt)
            if variant is not None:
                variant["type"] = blob["exercise"]["type"]
                REVIEW_VARIANTS[blob_id] = variant
                self._json({"blob": {**blob, "exercise": variant, "is_variant": True}})
            else:
                # graceful fallback: review the original stored exercise
                # rather than block review entirely if claude is unreachable
                REVIEW_VARIANTS.pop(blob_id, None)
                self._json({"blob": blob, "is_variant": False})
            return

        if path == "/api/graph":
            blob_id = (query.get("blob_id") or [None])[0]
            depth = int((query.get("depth") or ["4"])[0])
            content = load_content()
            graph = build_graph(content, blob_id, depth)
            self._json({"graph": graph})
            return

        if path == "/api/synthesis-challenge":
            content = load_content()
            progress = load_progress()
            blob_ids = recent_passed_blobs(content, progress, n=3)
            if len(blob_ids) < 2:
                self._json({"error": "Pass at least 2 exercises first, then a synthesis challenge can combine them."}, 400)
                return
            excerpts = []
            concepts = []
            for bid in blob_ids:
                _, b = find_blob(content, bid)
                excerpts.append((b["concept"], b.get("reading", "")))
                concepts.append(b["concept"])
            prompt = build_synthesis_prompt(content.get("title", "this book"), excerpts, content.get("language", "python"))
            result, error = call_claude_json(prompt)
            if result is None:
                self._json({"error": error or "Could not generate a synthesis challenge."}, 502)
                return
            challenge_id = str(time.time_ns())
            result["_excerpt"] = "\n\n".join(f"[{c}]\n{t}" for c, t in excerpts)
            result["_blob_ids"] = blob_ids
            SYNTHESIS_CHALLENGES[challenge_id] = result
            self._json({"challenge_id": challenge_id, "concepts": concepts, "challenge": result})
            return

        # static files
        rel = path.lstrip("/") or "index.html"
        file_path = (STATIC_DIR / rel).resolve()
        if STATIC_DIR not in file_path.parents and file_path != STATIC_DIR:
            self._json({"error": "forbidden"}, 403)
            return
        if not file_path.exists() or file_path.is_dir():
            file_path = STATIC_DIR / "index.html"
        content_type = {
            ".html": "text/html", ".js": "application/javascript",
            ".css": "text/css", ".json": "application/json",
        }.get(file_path.suffix, "application/octet-stream")
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        parsed = urlparse(self.path)
        body = self._read_json_body()

        if parsed.path == "/api/submit":
            content = load_content()
            progress = load_progress()
            blob_id = body["blob_id"]
            submission = body.get("code", "")
            chapter, blob = find_blob(content, blob_id)
            if not is_unlocked(content, progress, blob_id):
                self._json({"error": "blob is locked"}, 403)
                return
            exercise = blob["exercise"]

            if exercise["type"] == "implementation":
                passed, output = run_code_test(
                    content.get("language", "python"), submission, exercise["test_code"]
                )
            else:
                # short-answer: self-assessed, see /api/self-assess
                self._json({"error": "use /api/self-assess for short_answer exercises"}, 400)
                return

            state = progress["blobs"].setdefault(blob_id, {"status": "available", "box": 1, "last_reviewed": 0})
            attempts_before = state.get("attempts", 0)
            state["status"] = "passed" if passed else "available"
            state["box"] = leitner_advance(state.get("box", 1), passed, struggled=passed and attempts_before > 0)
            state["last_reviewed"] = time.time()
            state["attempts"] = attempts_before + 1
            state["draft"] = submission
            save_progress(progress)
            self._json({"passed": passed, "output": output})
            return

        if parsed.path == "/api/save-draft":
            content = load_content()
            progress = load_progress()
            blob_id = body["blob_id"]
            _, blob = find_blob(content, blob_id)
            if blob is None:
                self._json({"error": "unknown blob_id"}, 404)
                return
            state = progress["blobs"].setdefault(blob_id, {"status": "locked", "box": 1, "last_reviewed": 0})
            state["draft"] = body.get("code", "")
            save_progress(progress)
            self._json({"ok": True})
            return

        if parsed.path == "/api/self-assess":
            content = load_content()
            progress = load_progress()
            blob_id = body["blob_id"]
            if not is_unlocked(content, progress, blob_id):
                self._json({"error": "blob is locked"}, 403)
                return
            correct = bool(body.get("correct"))
            state = progress["blobs"].setdefault(blob_id, {"status": "available", "box": 1, "last_reviewed": 0})
            attempts_before = state.get("attempts", 0)
            state["status"] = "passed" if correct else "available"
            state["box"] = leitner_advance(state.get("box", 1), correct, struggled=correct and attempts_before > 0)
            state["last_reviewed"] = time.time()
            state["attempts"] = attempts_before + 1
            save_progress(progress)
            self._json({"ok": True})
            return

        if parsed.path == "/api/grade-answer":
            content = load_content()
            progress = load_progress()
            blob_id = body["blob_id"]
            if not is_unlocked(content, progress, blob_id):
                self._json({"error": "blob is locked"}, 403)
                return
            _, blob = find_blob(content, blob_id)
            exercise = blob["exercise"]
            answer = body.get("answer", "")
            follow_up_question = body.get("follow_up_question")
            follow_up_answer = body.get("follow_up_answer")

            prompt = build_grading_prompt(
                content.get("title", "this book"), blob.get("reading", ""),
                exercise.get("prompt", ""), exercise.get("expected_answer", ""),
                answer, follow_up_question, follow_up_answer,
            )
            result, error = call_claude_json(prompt)
            if result is None:
                self._json({"error": error or "grading failed"}, 502)
                return

            verdict = result.get("verdict")
            is_final = follow_up_question is not None or verdict != "partial"
            response = {
                "verdict": verdict,
                "feedback": result.get("feedback", ""),
                "final": is_final,
            }
            if is_final:
                state = progress["blobs"].setdefault(blob_id, {"status": "available", "box": 1, "last_reviewed": 0})
                attempts_before = state.get("attempts", 0)
                passed = verdict == "correct"
                state["status"] = "passed" if passed else "available"
                state["box"] = leitner_advance(state.get("box", 1), passed, struggled=passed and attempts_before > 0)
                state["last_reviewed"] = time.time()
                state["attempts"] = attempts_before + 1
                save_progress(progress)
            else:
                response["follow_up_question"] = result.get("follow_up_question")
            self._json(response)
            return

        if parsed.path == "/api/skip":
            content = load_content()
            progress = load_progress()
            blob_id = body["blob_id"]
            if not is_unlocked(content, progress, blob_id):
                self._json({"error": "blob is locked"}, 403)
                return
            state = progress["blobs"].setdefault(blob_id, {"status": "available", "box": 1, "last_reviewed": 0})
            state["status"] = "passed"
            state["skipped"] = True
            state["box"] = leitner_advance(state.get("box", 1), True)
            state["last_reviewed"] = time.time()
            save_progress(progress)
            self._json({"ok": True})
            return

        if parsed.path == "/api/reset":
            PROGRESS_PATH.unlink(missing_ok=True)
            self._json({"ok": True})
            return

        if parsed.path == "/api/shutdown":
            self._json({"ok": True})
            # Respond first, then exit shortly after on a separate thread -
            # calling shutdown()/exit() inline here would kill the response
            # we're still writing. Progress is already durable (written to
            # disk on every change), so an abrupt exit loses nothing.
            threading.Thread(target=_delayed_exit, daemon=True).start()
            return

        if parsed.path == "/api/hint":
            content = load_content()
            blob_id = body["blob_id"]
            level = int(body.get("level", 0))
            _, blob = find_blob(content, blob_id)
            hints = blob["exercise"].get("hints", [])
            hint = hints[level] if 0 <= level < len(hints) else None
            self._json({"hint": hint, "total_hints": len(hints)})
            return

        if parsed.path == "/api/review":
            content = load_content()
            blob_id = body["blob_id"]
            submission = body.get("code", "")
            _, blob = find_blob(content, blob_id)
            feedback = claude_review(
                content.get("title", "this book"),
                blob.get("reading", ""),
                blob["exercise"].get("prompt", ""),
                submission,
            )
            self._json({"feedback": feedback})
            return

        if parsed.path == "/api/review-submit":
            content = load_content()
            progress = load_progress()
            blob_id = body["blob_id"]
            _, blob = find_blob(content, blob_id)
            if blob is None:
                self._json({"error": "unknown blob_id"}, 404)
                return
            exercise = REVIEW_VARIANTS.get(blob_id) or blob["exercise"]

            if exercise["type"] == "implementation":
                passed, output = run_code_test(
                    content.get("language", "python"), body.get("code", ""), exercise["test_code"]
                )
                feedback = None
            else:
                prompt = build_grading_prompt(
                    content.get("title", "this book"), blob.get("reading", ""),
                    exercise.get("prompt", ""), exercise.get("expected_answer", ""),
                    body.get("answer", ""),
                )
                result, error = call_claude_json(prompt)
                if result is None:
                    self._json({"error": error or "grading failed"}, 502)
                    return
                passed = result.get("verdict") == "correct"
                output = None
                feedback = result.get("feedback")

            state = progress["blobs"].setdefault(blob_id, {"status": "passed", "box": 1, "last_reviewed": 0})
            state["box"] = leitner_advance(state.get("box", 1), passed)
            state["last_reviewed"] = time.time()
            state["attempts"] = state.get("attempts", 0) + 1
            save_progress(progress)
            REVIEW_VARIANTS.pop(blob_id, None)
            self._json({"passed": passed, "output": output, "feedback": feedback})
            return

        if parsed.path == "/api/synthesis-submit":
            challenge_id = body.get("challenge_id")
            challenge = SYNTHESIS_CHALLENGES.get(challenge_id)
            if challenge is None:
                self._json({"error": "unknown or expired challenge_id - request a new synthesis challenge"}, 404)
                return
            content = load_content()

            if challenge["type"] == "implementation":
                passed, output = run_code_test(
                    content.get("language", "python"), body.get("code", ""), challenge["test_code"]
                )
                apply_synthesis_result(challenge.get("_blob_ids", []), passed)
                self._json({"passed": passed, "output": output})
            else:
                prompt = build_grading_prompt(
                    content.get("title", "this book"), challenge.get("_excerpt", ""),
                    challenge.get("prompt", ""), challenge.get("expected_answer", ""),
                    body.get("answer", ""),
                )
                result, error = call_claude_json(prompt)
                if result is None:
                    self._json({"error": error or "grading failed"}, 502)
                    return
                passed = result.get("verdict") == "correct"
                apply_synthesis_result(challenge.get("_blob_ids", []), passed)
                self._json({"passed": passed, "feedback": result.get("feedback", "")})
            return

        self._json({"error": "not found"}, 404)


def main():
    if not CONTENT_PATH.exists():
        print(f"No content found at {CONTENT_PATH}. This app was not generated correctly.", file=sys.stderr)
        sys.exit(1)
    ensure_venv(load_content())
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8420
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"book-to-lab running at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
