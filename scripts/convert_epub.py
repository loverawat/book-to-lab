#!/usr/bin/env python3
"""
Convert an epub into per-chapter markdown files + a flat media/ folder,
using the epub's own spine order (not heading-guessing).

Usage:
    python3 convert_epub.py <book.epub> <output_dir>

Produces:
    <output_dir>/markdown/ch01_<slug>.md, ch02_<slug>.md, ...
    <output_dir>/media/<flattened image files>
    <output_dir>/manifest.json   (title, author, ordered chapter list)
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import unquote
import xml.etree.ElementTree as ET

NS = {
    "c": "urn:oasis:names:tc:opendocument:xmlns:container",
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
}


def slugify(text, maxlen=40):
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return (text or "untitled")[:maxlen]


def find_opf_path(root):
    container = root / "META-INF" / "container.xml"
    tree = ET.parse(container)
    rootfile = tree.find(".//c:rootfile", NS)
    return root / unquote(rootfile.get("full-path"))


def parse_opf(opf_path):
    tree = ET.parse(opf_path)
    root = tree.getroot()
    opf_dir = opf_path.parent

    title_el = root.find(".//dc:title", NS)
    author_el = root.find(".//dc:creator", NS)
    title = title_el.text.strip() if title_el is not None and title_el.text else "Untitled"
    author = author_el.text.strip() if author_el is not None and author_el.text else "Unknown"

    manifest = {}
    for item in root.findall(".//opf:manifest/opf:item", NS):
        manifest[item.get("id")] = {
            "href": item.get("href"),
            "media_type": item.get("media-type", ""),
        }

    spine_ids = [
        itemref.get("idref")
        for itemref in root.findall(".//opf:spine/opf:itemref", NS)
        if itemref.get("linear", "yes") != "no"
    ]

    spine_files = []
    for sid in spine_ids:
        item = manifest.get(sid)
        if item and "html" in item["media_type"]:
            spine_files.append((opf_dir / unquote(item["href"])).resolve())

    image_items = [
        (opf_dir / unquote(item["href"])).resolve()
        for item in manifest.values()
        if item["media_type"].startswith("image/")
    ]

    return title, author, spine_files, image_items


def build_media_map(image_paths, media_dir):
    media_dir.mkdir(parents=True, exist_ok=True)
    seen_names = {}
    path_to_flat = {}
    for img_path in image_paths:
        if not img_path.exists():
            continue
        base = img_path.name
        count = seen_names.get(base, 0)
        seen_names[base] = count + 1
        flat_name = base if count == 0 else f"{base.rsplit('.', 1)[0]}_{count}.{base.rsplit('.', 1)[-1]}"
        shutil.copy2(img_path, media_dir / flat_name)
        path_to_flat[str(img_path)] = flat_name
    return path_to_flat


IMG_LINK_RE = re.compile(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)')


def rewrite_image_links(markdown_text, chapter_file, media_map):
    def repl(match):
        alt, link = match.group(1), match.group(2)
        if link.startswith(("http://", "https://", "data:")):
            return match.group(0)
        resolved = str((chapter_file.parent / unquote(link)).resolve())
        flat = media_map.get(resolved)
        if flat:
            return f"![{alt}](media/{flat})"
        return match.group(0)

    return IMG_LINK_RE.sub(repl, markdown_text)


def convert_chapter(chapter_file, index, media_map, markdown_dir):
    result = subprocess.run(
        ["pandoc", "-f", "html", "-t", "gfm", str(chapter_file)],
        capture_output=True, text=True, check=True,
    )
    md = rewrite_image_links(result.stdout, chapter_file, media_map)

    heading_match = re.search(r"^#+\s+(.+)$", md, re.MULTILINE)
    title = heading_match.group(1).strip() if heading_match else chapter_file.stem
    slug = slugify(title)
    filename = f"ch{index:02d}_{slug}.md"
    (markdown_dir / filename).write_text(md, encoding="utf-8")
    return filename, title


def main():
    if len(sys.argv) != 3:
        print("Usage: convert_epub.py <book.epub> <output_dir>", file=sys.stderr)
        sys.exit(1)

    epub_path = Path(sys.argv[1]).expanduser().resolve()
    output_dir = Path(sys.argv[2]).expanduser().resolve()
    markdown_dir = output_dir / "markdown"
    media_dir = output_dir / "media"
    markdown_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(epub_path) as zf:
            zf.extractall(tmp_path)

        opf_path = find_opf_path(tmp_path)
        title, author, spine_files, image_paths = parse_opf(opf_path)

        media_map = build_media_map(image_paths, media_dir)

        chapters = []
        for i, chapter_file in enumerate(spine_files, start=1):
            if not chapter_file.exists():
                continue
            filename, chapter_title = convert_chapter(chapter_file, i, media_map, markdown_dir)
            chapters.append({"index": i, "file": filename, "title": chapter_title})

    manifest = {
        "title": title,
        "author": author,
        "source_epub": str(epub_path),
        "chapters": chapters,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Converted '{title}' by {author}: {len(chapters)} chapters, {len(media_map)} images.")
    print(f"Markdown: {markdown_dir}")
    print(f"Media:    {media_dir}")
    print(f"Manifest: {output_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()
