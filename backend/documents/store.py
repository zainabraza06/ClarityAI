"""
Document store using SQLite FTS5 for full-text search.

Documents (PDF, text, URLs) are chunked and indexed so the research agent
can retrieve relevant passages before running web searches.
"""

import re
import uuid
from pathlib import Path
from typing import List

import aiosqlite

DB_PATH = Path(__file__).parent.parent / "clarity_documents.db"

CHUNK_SIZE = 700    # words per chunk
CHUNK_OVERLAP = 80  # words of overlap between consecutive chunks

_STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "in", "of", "on", "at", "to", "for", "with", "this", "that", "these",
    "those", "and", "or", "but", "not", "it", "its", "as", "by", "from",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _chunk_text(text: str) -> List[str]:
    words = text.split()
    if not words:
        return []
    chunks: List[str] = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i : i + CHUNK_SIZE])
        chunks.append(chunk)
        if i + CHUNK_SIZE >= len(words):
            break
        i += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def _sanitize_fts(query: str) -> str:
    """Convert a free-form query into safe FTS5 OR-terms."""
    clean = re.sub(r"[^\w\s]", " ", query)
    terms = [
        w for w in clean.split()
        if len(w) > 2 and w.lower() not in _STOP_WORDS
    ][:10]
    return " OR ".join(terms) if terms else "research"


# ── DB lifecycle ───────────────────────────────────────────────────────────────

async def init_db() -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        # Try FTS5 with porter stemmer; fall back to default tokenizer if unavailable
        try:
            await db.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS doc_chunks USING fts5(
                    doc_id   UNINDEXED,
                    filename UNINDEXED,
                    content,
                    tokenize = 'porter ascii'
                )
            """)
        except Exception:
            await db.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS doc_chunks USING fts5(
                    doc_id   UNINDEXED,
                    filename UNINDEXED,
                    content
                )
            """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id           TEXT PRIMARY KEY,
                filename     TEXT NOT NULL,
                source_type  TEXT NOT NULL,
                chunk_count  INTEGER NOT NULL,
                uploaded_at  TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.commit()


# ── CRUD ───────────────────────────────────────────────────────────────────────

async def store_document(filename: str, source_type: str, text: str) -> dict:
    """Chunk and index a document. Returns document metadata."""
    chunks = _chunk_text(text)
    if not chunks:
        raise ValueError("Document produced no extractable text.")

    doc_id = str(uuid.uuid4())
    async with aiosqlite.connect(str(DB_PATH)) as db:
        for chunk in chunks:
            await db.execute(
                "INSERT INTO doc_chunks(doc_id, filename, content) VALUES (?, ?, ?)",
                (doc_id, filename, chunk),
            )
        await db.execute(
            "INSERT INTO documents(id, filename, source_type, chunk_count) VALUES (?, ?, ?, ?)",
            (doc_id, filename, source_type, len(chunks)),
        )
        await db.commit()

    return {
        "id": doc_id,
        "filename": filename,
        "source_type": source_type,
        "chunk_count": len(chunks),
    }


async def list_documents() -> List[dict]:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cursor = await db.execute(
            "SELECT id, filename, source_type, chunk_count, uploaded_at "
            "FROM documents ORDER BY uploaded_at DESC"
        )
        rows = await cursor.fetchall()
    return [
        {
            "id": r[0],
            "filename": r[1],
            "source_type": r[2],
            "chunk_count": r[3],
            "uploaded_at": r[4],
        }
        for r in rows
    ]


async def delete_document(doc_id: str) -> bool:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("DELETE FROM doc_chunks WHERE doc_id = ?", (doc_id,))
        cursor = await db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        await db.commit()
        return (cursor.rowcount or 0) > 0


async def search_chunks(query: str, limit: int = 6) -> List[dict]:
    """Full-text search across all stored document chunks."""
    fts_query = _sanitize_fts(query)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        try:
            cursor = await db.execute(
                "SELECT doc_id, filename, content "
                "FROM doc_chunks WHERE doc_chunks MATCH ? ORDER BY rank LIMIT ?",
                (fts_query, limit),
            )
            rows = await cursor.fetchall()
        except Exception:
            return []
    return [{"doc_id": r[0], "filename": r[1], "content": r[2]} for r in rows]
