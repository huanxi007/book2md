import io
import logging
import subprocess
import tempfile
import threading
from pathlib import Path

import pymupdf
import ebooklib
from ebooklib import epub
import html2text

logger = logging.getLogger(__name__)

SCANNED_THRESHOLD = 30

# Leptonica/tesseract is not thread-safe, serialize all OCR calls
_ocr_lock = threading.Lock()


def _ocr_page(page) -> str:
    """Render a PDF page to image and run OCR via PyMuPDF built-in."""
    with _ocr_lock:
        tp = page.get_textpage_ocr(flags=0, language="chi_sim+eng", dpi=150)
        text = page.get_text("text", textpage=tp).strip()
    return text


def _extract_text_page(page) -> str:
    """Extract text from a normal (non-scanned) PDF page with heading detection."""
    blocks = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)["blocks"]
    page_lines = []

    for block in blocks:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            spans = line["spans"]
            if not spans:
                continue
            text = "".join(s["text"] for s in spans).strip()
            if not text:
                continue

            max_size = max(s["size"] for s in spans)
            is_bold = any("bold" in s["font"].lower() for s in spans)

            if max_size >= 20:
                text = f"# {text}"
            elif max_size >= 16 and is_bold:
                text = f"## {text}"
            elif max_size >= 14 and is_bold:
                text = f"### {text}"
            elif is_bold:
                text = f"**{text}**"

            page_lines.append(text)

    return "\n\n".join(page_lines)


def convert_pdf_to_md(file_path: str, progress_cb=None) -> str:
    """Convert PDF to Markdown. Auto-detects scanned pages and uses OCR."""
    doc = pymupdf.open(file_path)
    total = len(doc)
    md_parts = []
    ocr_count = 0

    for page_num in range(total):
        page = doc[page_num]
        plain_text = page.get_text("text").strip()

        if len(plain_text) < SCANNED_THRESHOLD:
            text = _ocr_page(page)
            if text:
                ocr_count += 1
                md_parts.append(text)
        else:
            text = _extract_text_page(page)
            if text:
                md_parts.append(text)

        if progress_cb:
            progress_cb(page_num + 1, total)

    doc.close()

    if ocr_count > 0:
        logger.info(f"OCR applied to {ocr_count}/{total} pages in {Path(file_path).name}")

    return "\n\n---\n\n".join(md_parts)


def convert_epub_to_md(file_path: str, progress_cb=None) -> str:
    """Convert an EPUB file to Markdown using ebooklib + html2text."""
    book = epub.read_epub(file_path, options={"ignore_ncx": True})
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = False
    h.body_width = 0

    items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    total = len(items)
    md_parts = []
    for i, item in enumerate(items):
        html_content = item.get_content().decode("utf-8", errors="ignore")
        md_text = h.handle(html_content)
        if md_text.strip():
            md_parts.append(md_text.strip())
        if progress_cb:
            progress_cb(i + 1, total)

    return "\n\n---\n\n".join(md_parts)


EBOOK_FORMATS = {".mobi", ".azw", ".azw3", ".kfx", ".djvu", ".fb2", ".cbz", ".cbr"}


def _convert_to_epub(file_path: str) -> str:
    """Convert mobi/azw3/etc to EPUB using calibre's ebook-convert."""
    epub_path = str(Path(file_path).with_suffix(".epub"))
    result = subprocess.run(
        ["ebook-convert", file_path, epub_path],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ebook-convert failed: {result.stderr[-500:]}")
    return epub_path


def convert_file(file_path: str, progress_cb=None) -> str:
    """Convert a PDF or EPUB file to Markdown. Returns the markdown string."""
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return convert_pdf_to_md(file_path, progress_cb)
    elif ext == ".epub":
        return convert_epub_to_md(file_path, progress_cb)
    elif ext in EBOOK_FORMATS:
        logger.info(f"Converting {ext} to EPUB first via ebook-convert")
        epub_path = _convert_to_epub(file_path)
        return convert_epub_to_md(epub_path, progress_cb)
    else:
        raise ValueError(f"Unsupported file format: {ext}")
