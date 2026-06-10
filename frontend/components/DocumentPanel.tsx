"use client";

import { useEffect, useRef, useState } from "react";
import { StoredDocument } from "@/types";

interface DocumentPanelProps {
  onClose: () => void;
}

export default function DocumentPanel({ onClose }: DocumentPanelProps) {
  const [documents, setDocuments] = useState<StoredDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [urlInput, setUrlInput] = useState("");
  const [urlLabel, setUrlLabel] = useState("");
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchDocuments = async () => {
    try {
      const res = await fetch("/api/documents");
      const data = await res.json();
      setDocuments(data.documents ?? []);
    } catch {
      // ignore network errors during fetch
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError("");
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch("/api/documents/upload", { method: "POST", body: formData });
      if (res.ok) {
        await fetchDocuments();
      } else {
        const data = await res.json().catch(() => ({}));
        setError((data as { detail?: string }).detail ?? "Upload failed.");
      }
    } catch {
      setError("Network error during upload.");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleUrlFetch = async () => {
    const url = urlInput.trim();
    if (!url) return;
    setUploading(true);
    setError("");
    try {
      const res = await fetch("/api/documents/url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, label: urlLabel.trim() || undefined }),
      });
      if (res.ok) {
        setUrlInput("");
        setUrlLabel("");
        await fetchDocuments();
      } else {
        const data = await res.json().catch(() => ({}));
        setError((data as { detail?: string }).detail ?? "Failed to fetch URL.");
      }
    } catch {
      setError("Network error fetching URL.");
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      const res = await fetch(`/api/documents/${id}`, { method: "DELETE" });
      if (res.ok) setDocuments((prev) => prev.filter((d) => d.id !== id));
    } catch {
      // ignore
    }
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/10 z-40"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="fixed right-0 top-0 h-full w-72 bg-white border-l border-slate-200 shadow-2xl z-50 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 flex-shrink-0">
          <div className="flex items-center gap-2">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-brand-600">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
            </svg>
            <h2 className="text-sm font-semibold text-slate-800">Documents</h2>
            {documents.length > 0 && (
              <span className="text-xs bg-brand-100 text-brand-700 px-1.5 py-px rounded-full font-medium">
                {documents.length}
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Upload section */}
        <div className="px-4 py-3 border-b border-slate-100 flex-shrink-0 space-y-2.5">
          <p className="text-xs text-slate-500 leading-relaxed">
            Uploaded documents are searched on every query and included in research context.
          </p>

          {/* File upload */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.txt"
            onChange={handleFileSelect}
            className="hidden"
          />
          <button
            type="button"
            disabled={uploading}
            onClick={() => fileInputRef.current?.click()}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 border border-dashed border-slate-300 rounded-lg text-xs text-slate-600 hover:border-brand-400 hover:text-brand-600 transition disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            {uploading ? "Uploading…" : "Upload PDF or .txt"}
          </button>

          {/* URL ingestion */}
          <div className="space-y-1">
            <div className="flex gap-1.5">
              <input
                type="url"
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleUrlFetch()}
                placeholder="Paste a URL to ingest…"
                disabled={uploading}
                className="flex-1 text-xs px-2.5 py-1.5 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-brand-500 disabled:opacity-40 placeholder-slate-300"
              />
              <button
                type="button"
                disabled={uploading || !urlInput.trim()}
                onClick={handleUrlFetch}
                className="px-2.5 py-1.5 bg-brand-600 text-white text-xs rounded-lg hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed transition"
              >
                Fetch
              </button>
            </div>
            {urlInput.trim() && (
              <input
                type="text"
                value={urlLabel}
                onChange={(e) => setUrlLabel(e.target.value)}
                placeholder="Label (optional)"
                className="w-full text-xs px-2.5 py-1 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-brand-500 placeholder-slate-300"
              />
            )}
          </div>

          {error && (
            <p className="text-xs text-red-500 flex items-start gap-1">
              <span className="flex-shrink-0 mt-px">⚠</span>
              <span>{error}</span>
            </p>
          )}
        </div>

        {/* Document list */}
        <div className="flex-1 overflow-y-auto custom-scroll">
          {loading ? (
            <p className="text-xs text-slate-400 text-center py-8">Loading…</p>
          ) : documents.length === 0 ? (
            <div className="text-center py-10 px-4">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-slate-200 mx-auto mb-3">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
              </svg>
              <p className="text-xs text-slate-400">No documents yet.</p>
              <p className="text-xs text-slate-300 mt-1">Upload a PDF, .txt, or paste a URL above.</p>
            </div>
          ) : (
            <div className="py-2">
              {documents.map((doc) => (
                <DocItem key={doc.id} doc={doc} onDelete={handleDelete} />
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

// ── Document list item ─────────────────────────────────────────────────────────

function DocItem({
  doc,
  onDelete,
}: {
  doc: StoredDocument;
  onDelete: (id: string) => void;
}) {
  return (
    <div className="group flex items-start gap-2.5 px-4 py-2.5 hover:bg-slate-50 transition">
      <span className="mt-0.5 flex-shrink-0 text-slate-400">
        {doc.source_type === "pdf" ? <PdfIcon /> : doc.source_type === "url" ? <LinkIcon /> : <TxtIcon />}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-slate-700 truncate leading-snug">{doc.filename}</p>
        <p className="text-[10px] text-slate-400 mt-0.5">
          {doc.chunk_count} chunk{doc.chunk_count !== 1 ? "s" : ""} · {formatDate(doc.uploaded_at)}
        </p>
      </div>
      <button
        type="button"
        onClick={() => onDelete(doc.id)}
        title="Remove document"
        className="opacity-0 group-hover:opacity-100 mt-0.5 p-0.5 text-slate-300 hover:text-red-400 transition flex-shrink-0"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polyline points="3 6 5 6 21 6" />
          <path d="M19 6l-1 14H6L5 6" />
          <path d="M10 11v6M14 11v6" />
          <path d="M9 6V4h6v2" />
        </svg>
      </button>
    </div>
  );
}

// ── Icons ──────────────────────────────────────────────────────────────────────

function PdfIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}

function LinkIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
    </svg>
  );
}

function TxtIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
    </svg>
  );
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
