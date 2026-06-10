"""
Document management API routes.

Supports uploading PDF / plain-text files and ingesting web URLs.
All documents are stored in SQLite FTS5 and searched automatically
by the research agent on every query.
"""

import io
import logging
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from documents.store import delete_document, list_documents, store_document

logger = logging.getLogger("clarityai.documents")
document_router = APIRouter(prefix="/api/documents")


# ── HTML stripping ─────────────────────────────────────────────────────────────

class _TextStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_tags = {"script", "style", "head", "nav", "footer", "noscript"}
        self._in_skip = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self._skip_tags:
            self._in_skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._skip_tags and self._in_skip > 0:
            self._in_skip -= 1

    def handle_data(self, data: str) -> None:
        if self._in_skip == 0:
            stripped = data.strip()
            if stripped:
                self._parts.append(stripped)

    def get_text(self) -> str:
        return " ".join(self._parts)


def _strip_html(html: str) -> str:
    s = _TextStripper()
    s.feed(html)
    return s.get_text()


def _parse_pdf(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ValueError("pypdf is not installed — cannot parse PDF files.")
    reader = PdfReader(io.BytesIO(content))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(p for p in pages if p.strip())


# ── Endpoints ──────────────────────────────────────────────────────────────────

@document_router.get("")
async def list_docs():
    """Return all uploaded documents."""
    docs = await list_documents()
    return {"documents": docs}


@document_router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    Upload a PDF or plain-text file.
    The document is chunked and indexed for full-text search.
    """
    content = await file.read()
    filename = file.filename or "untitled"
    content_type = (file.content_type or "").lower()

    if filename.lower().endswith(".pdf") or "pdf" in content_type:
        try:
            text = _parse_pdf(content)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        source_type = "pdf"

    elif filename.lower().endswith(".txt") or "text/plain" in content_type:
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Could not read text file: {exc}")
        source_type = "txt"

    else:
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type. Upload a PDF (.pdf) or plain-text (.txt) file.",
        )

    text = text.strip()
    if len(text) < 50:
        raise HTTPException(status_code=422, detail="Document appears empty or unreadable.")

    try:
        doc = await store_document(filename, source_type, text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    logger.info("Document uploaded: %s  (%d chunks)", filename, doc["chunk_count"])
    return doc


class UrlIngestRequest(BaseModel):
    url: str
    label: Optional[str] = None


@document_router.post("/url")
async def ingest_url(request: UrlIngestRequest):
    """
    Fetch a public web page and index its text content.
    """
    url = request.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    try:
        async with httpx.AsyncClient(
            timeout=20, follow_redirects=True, max_redirects=5
        ) as client:
            resp = await client.get(url, headers={"User-Agent": "ClarityAI/1.0"})
            resp.raise_for_status()
            html = resp.text
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=422, detail=f"URL returned HTTP {exc.response.status_code}"
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to fetch URL: {exc}")

    text = _strip_html(html).strip()
    if len(text) < 100:
        raise HTTPException(
            status_code=422, detail="Could not extract enough text from the URL."
        )

    label = request.label or urlparse(url).netloc or url[:60]
    try:
        doc = await store_document(label, "url", text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    logger.info("URL ingested: %s  (%d chunks)", label, doc["chunk_count"])
    return doc


@document_router.delete("/{doc_id}")
async def delete_doc(doc_id: str):
    deleted = await delete_document(doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"ok": True}
