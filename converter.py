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


def _get_evernote_note_store():
    """Get Evernote NoteStore client using token from macOS Keychain."""
    import inspect
    if not hasattr(inspect, 'getargspec'):
        inspect.getargspec = inspect.getfullargspec

    import subprocess as sp
    # Try both account IDs
    token = None
    for acct in ["6747163/Evernote-China/smd", "27295961/Evernote-China/smd"]:
        try:
            raw = sp.check_output(
                ["security", "find-generic-password", "-s", "Evernote", "-a", acct, "-w"],
                stderr=sp.DEVNULL,
            )
            import plistlib
            plist = plistlib.loads(bytes.fromhex(raw.decode().strip()))
            objects = plist.get("$objects", [])
            for obj in objects:
                if isinstance(obj, str) and obj.startswith("S=s"):
                    token = obj
                    break
            if token:
                break
        except Exception:
            continue

    if not token:
        return None, None

    from evernote.api.client import EvernoteClient
    client = EvernoteClient(token=token, sandbox=False, service_host="app.yinxiang.com")
    note_store = client.get_note_store()
    return note_store, token


def _fetch_note_content_by_title(title: str) -> str | None:
    """Fetch note ENML content from Evernote API by title."""
    try:
        note_store, token = _get_evernote_note_store()
        if not note_store:
            return None

        from evernote.edam.notestore.ttypes import NoteFilter, NotesMetadataResultSpec
        nf = NoteFilter()
        nf.words = f'intitle:"{title}"'
        spec = NotesMetadataResultSpec()
        spec.includeTitle = True

        results = note_store.findNotesMetadata(token, nf, 0, 5, spec)
        for meta in results.notes:
            if meta.title == title:
                note = note_store.getNote(token, meta.guid, True, False, False, False)
                content = note.content
                if isinstance(content, bytes):
                    content = content.decode("utf-8", errors="ignore")
                return content
    except Exception as e:
        logger.warning(f"Evernote API fetch failed: {e}")
    return None


def convert_enex_to_md(file_path: str, progress_cb=None) -> str:
    """Convert Evernote .enex/.notes file to Markdown."""
    import xml.etree.ElementTree as ET
    import base64

    tree = ET.parse(file_path)
    root = tree.getroot()
    notes = root.findall("note")
    total = len(notes)
    md_parts = []

    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = False
    h.body_width = 0

    for i, note in enumerate(notes):
        title_el = note.find("title")
        content_el = note.find("content")
        created_el = note.find("created")

        title = title_el.text if title_el is not None else "Untitled"
        parts = [f"# {title}"]

        if created_el is not None and created_el.text:
            ts = created_el.text
            date_str = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
            parts.append(f"*{date_str}*")

        if content_el is not None and content_el.text:
            encoding = content_el.get("encoding", "")
            if "aes" in encoding:
                # Encrypted - try fetching from Evernote API
                logger.info(f"Note '{title}' is encrypted, fetching via API...")
                api_content = _fetch_note_content_by_title(title)
                if api_content:
                    md_text = h.handle(api_content)
                    if md_text.strip():
                        parts.append(md_text.strip())
                    logger.info(f"Successfully decrypted '{title}' via API")
                else:
                    parts.append("> [内容已加密，且无法通过 API 获取。请在印象笔记中导出为 .enex 格式]")
            elif "base64" in encoding:
                try:
                    html_content = base64.b64decode(content_el.text).decode("utf-8", errors="ignore")
                    md_text = h.handle(html_content)
                    if md_text.strip():
                        parts.append(md_text.strip())
                except Exception:
                    parts.append(content_el.text[:200] + "...")
            else:
                html_content = content_el.text
                md_text = h.handle(html_content)
                if md_text.strip():
                    parts.append(md_text.strip())

        md_parts.append("\n\n".join(parts))

        if progress_cb:
            progress_cb(i + 1, total)

    return "\n\n---\n\n".join(md_parts)


def convert_xml_to_md(file_path: str, progress_cb=None) -> str:
    """Convert XML file to Markdown. Handles HTML-like XML and structured XML."""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if progress_cb:
        progress_cb(0, 1)

    # If it looks like HTML/XHTML, use html2text
    if "<html" in content.lower() or "<body" in content.lower():
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = False
        h.body_width = 0
        result = h.handle(content)
    else:
        # Structured XML: parse and convert to readable Markdown
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(content)
            result = _xml_node_to_md(root, level=0)
        except ET.ParseError:
            # Fallback: strip tags with html2text
            h = html2text.HTML2Text()
            h.body_width = 0
            result = h.handle(content)

    if progress_cb:
        progress_cb(1, 1)

    return result.strip()


def _xml_node_to_md(node, level=0) -> str:
    """Recursively convert XML node tree to Markdown."""
    parts = []
    tag = node.tag.split("}")[-1] if "}" in node.tag else node.tag  # strip namespace

    # Node text
    text = (node.text or "").strip()
    children = list(node)

    if not children and text:
        # Leaf node with text
        if level <= 2:
            prefix = "#" * (level + 1) + " " if level < 3 else "**"
            suffix = "" if level < 3 else "**"
            parts.append(f"{prefix}{tag}{suffix}\n\n{text}")
        else:
            parts.append(f"**{tag}**: {text}")
    elif children:
        # Parent node
        if level < 3:
            parts.append(f"{'#' * (level + 1)} {tag}")
        if text:
            parts.append(text)
        for child in children:
            parts.append(_xml_node_to_md(child, level + 1))

    # Tail text
    tail = (node.tail or "").strip()
    if tail:
        parts.append(tail)

    return "\n\n".join(parts)


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
    elif ext in (".enex", ".notes"):
        return convert_enex_to_md(file_path, progress_cb)
    elif ext == ".xml":
        return convert_xml_to_md(file_path, progress_cb)
    elif ext in EBOOK_FORMATS:
        logger.info(f"Converting {ext} to EPUB first via ebook-convert")
        epub_path = _convert_to_epub(file_path)
        return convert_epub_to_md(epub_path, progress_cb)
    else:
        raise ValueError(f"Unsupported file format: {ext}")
