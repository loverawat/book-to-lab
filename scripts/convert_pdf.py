#!/usr/bin/env python3
"""
Convert a PDF into per-chapter markdown files + a flat media/ folder,
mirroring convert_epub.py's output contract exactly (same markdown/
media/manifest.json shape) so Phase 2 generation never needs to know
which input format produced them.

PDF has none of epub's structural guarantees: no spine/manifest (chapter
structure is inferred, not read - see get_outline_chapters/
find_heading_candidates), and no semantic math markup (math is detected
by embedded font name, then rasterized as an image rather than
extracted as text - see is_math_font). This is a best-effort mechanical
pass, not a solved conversion the way epub's is. See CLAUDE.md for the
full design rationale and its known limitations.

Usage:
    python3 convert_pdf.py <book.pdf> <output_dir>

Produces the same shape as convert_epub.py, plus a chapter_confidence
field in manifest.json ("outline" | "heuristic" | "none") so Phase 2
generation knows how much to trust the chapter split it's been handed:
    <output_dir>/markdown/ch01_<slug>.md, ch02_<slug>.md, ...
    <output_dir>/media/<flattened image + rasterized-math files>
    <output_dir>/manifest.json

Needs pymupdf, which is a dependency of this script's own tooling, not
of the skill or the generated app (see CLAUDE.md's "skill-tooling venv"
design-decision note). Not installed system-wide or into any book's
per-book venv - this script lazily creates its own isolated venv under
<skill_dir>/.venv the first time it runs and re-execs itself under it,
so it can be invoked as plain `python3 convert_pdf.py ...` under
whatever python3 happens to be on PATH, the same way convert_epub.py is.
"""
import os
import re
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path

# --- self-bootstrap into an isolated venv for pymupdf, before importing it ---

SKILL_DIR = Path(__file__).resolve().parent.parent
SKILL_VENV_DIR = SKILL_DIR / ".venv"
SKILL_VENV_MARKER = SKILL_VENV_DIR / ".deps_installed"


def _skill_venv_python():
    for candidate in (SKILL_VENV_DIR / "bin" / "python3", SKILL_VENV_DIR / "Scripts" / "python.exe"):
        if candidate.exists():
            return str(candidate)
    return None


def _ensure_skill_venv():
    """Lazily create a venv for this skill's own conversion tooling (not
    any generated book's app - see CLAUDE.md) and install pymupdf into
    it. Gates on a marker written only after install succeeds, not on
    the venv directory existing, for the same reason
    app-engine/server.py's ensure_venv() does: venv creation happens
    before the package is installed into it, so an interrupted first
    run would otherwise look "already set up" forever."""
    if SKILL_VENV_MARKER.exists():
        return _skill_venv_python()
    print("Setting up an isolated environment for PDF conversion (pymupdf)...")
    if not _skill_venv_python():
        subprocess.run([sys.executable, "-m", "venv", str(SKILL_VENV_DIR)], check=True)
    subprocess.run([_skill_venv_python(), "-m", "pip", "install", "--quiet", "pymupdf"], check=True)
    SKILL_VENV_MARKER.write_text("ok", encoding="utf-8")
    print("Done - this only happens once.")
    return _skill_venv_python()


def _relaunch_in_skill_venv():
    """If not already running under the skill venv's interpreter, set it
    up (if needed) and re-exec this same script under it, so the rest of
    this file can `import pymupdf` directly instead of every caller
    needing to know which interpreter to invoke this with.

    Checks sys.prefix, not sys.executable - a venv's interpreter is
    typically a symlink back to the base install, so comparing resolved
    executable *paths* collapses to the same file and always looks like
    a match. sys.prefix reflects which environment is actually active
    (its site-packages root) regardless of that symlink."""
    venv_python = _ensure_skill_venv()
    if Path(sys.prefix).resolve() == SKILL_VENV_DIR.resolve():
        return
    os.execv(venv_python, [venv_python, str(Path(__file__).resolve()), *sys.argv[1:]])


_relaunch_in_skill_venv()

import json  # noqa: E402
import pymupdf  # noqa: E402


def slugify(text, maxlen=40):
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return (text or "untitled")[:maxlen]


# --- math font detection ---

# Known LaTeX/XeLaTeX/professional math-typesetting font family names.
# Catches the common case of a real technical/academic PDF typeset with a
# real math package; misses PDFs that embed math a different way (e.g.
# Word's own equation editor). Implemented from documented, decades-stable
# font-naming conventions - NOT verified against a real LaTeX-produced PDF
# in this environment, since no LaTeX distribution was available to
# generate one. Verified instead against a synthetic PDF with a real font
# file renamed to a known math-font name (fontTools), which exercises the
# same code path (span font-name -> classified as math -> rasterized) but
# isn't the same as seeing it against a document LaTeX actually produced.
MATH_FONT_MARKERS = (
    "cmmi", "cmsy", "cmex", "cmbsy", "cmmib",  # Computer Modern math families
    "lmmi", "lmsy", "lmex", "latinmodernmath", "lmmath",  # Latin Modern Math
    "stixmath", "stix2math", "xitsmath",
    "asanamath", "texgyremath", "cambriamath",
    "mnsymbol", "mathtime",
)


def is_math_font(font_name):
    name = (font_name or "").lower().replace(" ", "").replace("-", "")
    return any(marker in name for marker in MATH_FONT_MARKERS)


# --- chapter structure: outline first, heuristic fallback ---

def get_outline_chapters(doc):
    """Top-level (depth 1) outline/bookmark entries only - deeper levels
    are left as sections within a chapter, matching the granularity
    Phase 2 already expects to find and chunk within one converted
    chapter file. Returns [] if the PDF has no outline at all."""
    toc = doc.get_toc()  # [[level, title, 1-indexed page], ...]
    return [(title, page - 1) for level, title, page in toc if level == 1 and page >= 1]


CHAPTER_PATTERNS = (
    re.compile(r"^(chapter|part)\s+\w+", re.IGNORECASE),
    re.compile(r"^\d+(\.\d+)*\s+[A-Z]"),
    re.compile(r"^[A-Z][A-Z0-9 \t:'-]{3,60}$"),  # short ALL-CAPS line
)


def find_heading_candidates(doc):
    """Font-size + pattern heuristic, used only when there's no outline.
    A line counts as a heading candidate if it's meaningfully larger than
    the document's body text size AND either matches a chapter-like
    pattern or is dramatically larger (>=1.6x body size) - two weak
    signals corroborating each other, to avoid flagging every bolded
    pull-quote or emphasized sentence as a chapter start."""
    sizes = []
    lines_by_page = []
    for page_index in range(doc.page_count):
        page = doc[page_index]
        d = page.get_text("dict")
        page_lines = []
        for block in d["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                text = "".join(s["text"] for s in spans).strip()
                if not text:
                    continue
                size = max(s["size"] for s in spans)
                sizes.append(round(size))
                page_lines.append({"text": text, "size": size})
        lines_by_page.append(page_lines)

    if not sizes:
        return []
    body_size = statistics.mode(sizes)

    candidates = []
    for page_index, page_lines in enumerate(lines_by_page):
        for line in page_lines:
            if line["size"] < body_size * 1.3 or len(line["text"]) > 80:
                continue
            matches_pattern = any(p.search(line["text"]) for p in CHAPTER_PATTERNS)
            if matches_pattern or line["size"] >= body_size * 1.6:
                candidates.append((line["text"], page_index))
    return candidates


def dedupe_candidates(candidates, min_page_gap=1):
    """Collapse candidates that land on the same or adjacent pages (a
    heading can produce more than one oversized line - title + subtitle)
    into a single chapter start, keeping the first."""
    out = []
    last_page = None
    for title, page in candidates:
        if last_page is not None and page - last_page < min_page_gap:
            continue
        out.append((title, page))
        last_page = page
    return out


def determine_chapters(doc):
    """Returns (chapters, confidence). chapters is a list of
    (title, start_page) tuples covering the whole document."""
    outline = get_outline_chapters(doc)
    if outline:
        return outline, "outline"

    candidates = dedupe_candidates(find_heading_candidates(doc))
    if len(candidates) >= 2:
        return candidates, "heuristic"

    title = (doc.metadata or {}).get("title") or ""
    return [(title.strip() or "Full text", 0)], "none"


# --- running header/footer stripping ---

def normalize_line(line):
    return re.sub(r"\d+", "#", line.strip())


def find_boilerplate_lines(pages):
    """pages: list of per-page (plain, markdown) line-pair lists, for the
    WHOLE document - must be computed document-wide, not per-chapter,
    since a running header/footer needs enough pages to recur across
    before it's distinguishable from real content (a 2-page chapter
    never has enough of its own pages to hit a repetition threshold).
    A line counts as boilerplate if a digit-normalized version of it
    recurs as the first-or-last line on a large fraction of pages."""
    counts = Counter()
    n = len(pages)
    for page_lines in pages:
        plain = [p for p, _ in page_lines if p]
        if not plain:
            continue
        for line in (plain[0], plain[-1]):
            norm = normalize_line(line)
            if norm:
                counts[norm] += 1

    threshold = max(3, int(n * 0.4))
    return {norm for norm, c in counts.items() if c >= threshold}


# --- per-page extraction: text, images, math regions, in reading order ---

class MediaWriter:
    def __init__(self, media_dir):
        self.media_dir = media_dir
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.image_count = 0
        self.math_count = 0

    def save_image(self, data, ext):
        self.image_count += 1
        name = f"pdf_img_{self.image_count:03d}.{ext}"
        (self.media_dir / name).write_bytes(data)
        return name

    def save_math(self, page, bbox):
        self.math_count += 1
        name = f"pdf_eq_{self.math_count:03d}.png"
        pad = 2  # a little breathing room so ascenders/descenders aren't clipped
        clip = pymupdf.Rect(bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad)
        pix = page.get_pixmap(clip=clip, dpi=200)
        pix.save(self.media_dir / name)
        return name


def merge_runs(spans):
    """Given a line's spans (each with text/font/bbox), merge adjacent
    spans that agree on math-vs-text classification into runs, so a
    contiguous sequence of math-font glyphs becomes one rasterized
    region instead of one image per glyph run."""
    runs = []
    for span in spans:
        is_math = is_math_font(span["font"])
        if runs and runs[-1]["is_math"] == is_math:
            runs[-1]["text"] += span["text"]
            b = runs[-1]["bbox"]
            sb = span["bbox"]
            runs[-1]["bbox"] = (min(b[0], sb[0]), min(b[1], sb[1]), max(b[2], sb[2]), max(b[3], sb[3]))
        else:
            runs.append({"is_math": is_math, "text": span["text"], "bbox": span["bbox"]})
    return runs


def extract_page_lines(page, media):
    """Returns a list of (plain_text, markdown_text) pairs, one per
    line/image block on this page, in reading order. Deliberately one
    combined list rather than two parallel ones (plain_lines, md_parts)
    - two lists that are supposed to stay index-aligned but don't always
    grow together (an image block has no plain-text line of its own) is
    exactly the kind of thing that silently drifts out of sync; found
    via testing, not assumed. plain_text is "" for an image/math line,
    which normalize_line() turns into "" too, so it can never match a
    real boilerplate entry - correct, since an image can't be a running
    header/footer."""
    d = page.get_text("dict")
    out = []

    for block in d["blocks"]:
        if block.get("type") == 1:  # image block
            ext = block.get("ext", "png")
            data = block.get("image")
            if data:
                name = media.save_image(data, ext)
                out.append(("", f"![]({name})"))
            continue

        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            plain = "".join(s["text"] for s in spans).strip()

            runs = merge_runs(spans)
            line_md = ""
            for run in runs:
                if not run["text"].strip():
                    line_md += run["text"]
                elif run["is_math"]:
                    name = media.save_math(page, run["bbox"])
                    line_md += f"[MATH: {name}]"
                else:
                    line_md += run["text"]
            out.append((plain, line_md))

    return out


def assemble_chapter(index, title, page_range, pages, boilerplate, markdown_dir):
    """page_range is (start_page, end_page); pages is the full document's
    pre-extracted per-page (plain, markdown) line pairs (see main()) -
    this only slices and filters, it doesn't re-extract."""
    body_lines = []
    for page_index in range(*page_range):
        for plain, md_line in pages[page_index]:
            if plain and normalize_line(plain) in boilerplate:
                continue
            body_lines.append(md_line)

    slug = slugify(title)
    filename = f"ch{index:02d}_{slug}.md"
    text = f"# {title}\n\n" + "\n\n".join(l for l in body_lines if l.strip())
    (markdown_dir / filename).write_text(text, encoding="utf-8")
    return filename


def main():
    if len(sys.argv) != 3:
        print("Usage: convert_pdf.py <book.pdf> <output_dir>", file=sys.stderr)
        sys.exit(1)

    pdf_path = Path(sys.argv[1]).expanduser().resolve()
    output_dir = Path(sys.argv[2]).expanduser().resolve()
    markdown_dir = output_dir / "markdown"
    media_dir = output_dir / "media"
    markdown_dir.mkdir(parents=True, exist_ok=True)

    doc = pymupdf.open(str(pdf_path))
    meta = doc.metadata or {}
    title = (meta.get("title") or pdf_path.stem).strip() or pdf_path.stem
    author = (meta.get("author") or "Unknown").strip() or "Unknown"

    chapters_raw, confidence = determine_chapters(doc)
    boundaries = [page for _, page in chapters_raw] + [doc.page_count]

    # Extract every page exactly once, up front - both because boilerplate
    # detection needs document-wide data (see find_boilerplate_lines) and
    # because it means each page's images/math only ever get rasterized
    # once regardless of chapter boundaries.
    media = MediaWriter(media_dir)
    pages = [extract_page_lines(doc[page_index], media) for page_index in range(doc.page_count)]

    boilerplate = find_boilerplate_lines(pages)

    chapters = []
    for i, (chapter_title, start_page) in enumerate(chapters_raw, start=1):
        end_page = boundaries[i]
        if end_page <= start_page:
            continue
        title_clean = chapter_title.strip() or f"Chapter {i}"
        filename = assemble_chapter(
            i, title_clean, (start_page, end_page), pages, boilerplate, markdown_dir
        )
        chapters.append({"index": i, "file": filename, "title": title_clean})

    manifest = {
        "title": title,
        "author": author,
        "source_pdf": str(pdf_path),
        "chapters": chapters,
        "chapter_confidence": confidence,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Converted '{title}' by {author}: {len(chapters)} chapters "
          f"(chapter structure confidence: {confidence}), "
          f"{media.image_count} images, {media.math_count} math regions.")
    print(f"Markdown: {markdown_dir}")
    print(f"Media:    {media_dir}")
    print(f"Manifest: {output_dir / 'manifest.json'}")
    if confidence != "outline":
        print(
            "NOTE: this PDF had no usable outline/bookmarks, so chapter "
            "boundaries were inferred (confidence: "
            f"{confidence}). Skim the converted markdown and use "
            "judgment about the split before treating it as reliable - "
            "see SKILL.md."
        )


if __name__ == "__main__":
    main()
