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
import subprocess
import sys
import tempfile
import textwrap
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
        try:
            result = subprocess.run(
                runner["cmd"](test_file),
                cwd=tmp_path,
                capture_output=True,
                text=True,
                timeout=EXEC_TIMEOUT_SECS,
            )
            passed = result.returncode == 0
            output = (result.stdout or "") + (result.stderr or "")
        except subprocess.TimeoutExpired:
            passed = False
            output = f"Timed out after {EXEC_TIMEOUT_SECS}s (possible infinite loop)."
    return passed, output.strip()


def leitner_advance(box, passed):
    if passed:
        return min(box + 1, 5)
    return 1


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
            self._json({"blob": blob})
            return

        if path == "/api/graph":
            blob_id = (query.get("blob_id") or [None])[0]
            depth = int((query.get("depth") or ["4"])[0])
            content = load_content()
            graph = build_graph(content, blob_id, depth)
            self._json({"graph": graph})
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
            state["status"] = "passed" if passed else "available"
            state["box"] = leitner_advance(state.get("box", 1), passed)
            state["last_reviewed"] = time.time()
            state["attempts"] = state.get("attempts", 0) + 1
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
            state["status"] = "passed" if correct else "available"
            state["box"] = leitner_advance(state.get("box", 1), correct)
            state["last_reviewed"] = time.time()
            state["attempts"] = state.get("attempts", 0) + 1
            save_progress(progress)
            self._json({"ok": True})
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
