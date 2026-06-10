# ClarityAI — Multi-Agent Business Research Assistant

> AI-powered business intelligence through collaborative multi-agent reasoning, real-time financial data, and document-grounded research.

---

## Table of Contents

1. [Overview](#overview)
2. [Feature Catalogue](#feature-catalogue)
3. [System Architecture](#system-architecture)
4. [Multi-Agent Pipeline](#multi-agent-pipeline)
5. [Agent Reference](#agent-reference)
6. [LLM Fallback Chain](#llm-fallback-chain)
7. [Research Data Sources](#research-data-sources)
8. [Document Ingestion Pipeline](#document-ingestion-pipeline)
9. [State Management & Persistence](#state-management--persistence)
10. [SSE Streaming Flow](#sse-streaming-flow)
11. [Report Templates](#report-templates)
12. [Frontend Architecture](#frontend-architecture)
13. [Tech Stack](#tech-stack)
14. [Project Structure](#project-structure)
15. [Prerequisites](#prerequisites)
16. [Setup & Running](#setup--running)
17. [Environment Variables](#environment-variables)
18. [API Reference](#api-reference)
19. [Multi-Turn Conversation](#multi-turn-conversation)
20. [Technical Design Decisions](#technical-design-decisions)

---

## Overview

ClarityAI is a self-hosted, multi-agent business research assistant. A user submits a natural-language query about any company and four specialized AI agents collaborate in a directed graph to produce a structured, sourced intelligence report.

What separates it from single-prompt AI tools:

- **Transparent reasoning** — the UI shows each agent activating and completing in real time
- **Quality control loop** — a Validator agent scores research quality and can trigger re-research before any report is written
- **Real financial data** — Yahoo Finance is queried for every company, adding real market cap, revenue, P/E, and growth metrics that LLM training data cannot provide
- **Document-grounded research** — upload PDFs, text files, or web pages; their content is searched on every query
- **Persistent memory** — conversation threads survive server restarts via SQLite checkpointing
- **Five report templates** — Standard, Investor Memo, Competitor Analysis, SWOT, Comparison

---

## Feature Catalogue

### Research & Intelligence
| Feature | Description |
|---|---|
| Multi-agent pipeline | 4 agents with distinct roles; coordinated by LangGraph StateGraph |
| Real-time web search | Tavily MCP server (spawned via `npx`) with up to 3 ReAct search rounds |
| Real financial data | Yahoo Finance via `yfinance` — market cap, revenue, margins, P/E, EPS, growth |
| Document ingestion | Upload PDF / `.txt` files or ingest any URL; searched on every query via SQLite FTS5 |
| Confidence scoring | Research agent self-evaluates data completeness (0–10); drives retry logic |
| Validation loop | Validator agent independently assesses research quality; retries up to 3× |
| Source citations | Source URLs collected from Tavily results and appended to every report |

### Conversation & Memory
| Feature | Description |
|---|---|
| Multi-turn threads | `thread_id` keys conversation state; follow-up questions preserve context |
| Persistent checkpoints | SQLite-backed LangGraph checkpointer survives server restarts |
| Clarification interrupts | Graph pauses mid-execution when a query is ambiguous; resumes after user responds |
| Conversation history | All chats saved to `localStorage`; restore any past session from the sidebar |

### Report Formats
| Template | Output format |
|---|---|
| Standard | Business overview, recent developments, financials, risks & opportunities |
| Investor Memo | Executive summary, investment thesis, financial highlights, risks |
| Competitor Analysis | Competitive landscape, moats, weaknesses, market positioning |
| SWOT | Strengths / Weaknesses / Opportunities / Threats with strategic summary |
| Comparison | Side-by-side table + verdict for two companies |

### UI / UX
| Feature | Description |
|---|---|
| Live agent timeline | Each agent shown as running → completed with output details in real time |
| Template selector | Five pill-shaped template options above the input; template-specific placeholder text |
| Confidence badge | Color-coded badge (green ≥ 7, amber 4–6, red < 4) on every assistant message |
| Copy to clipboard | One-click copy of the full Markdown report |
| Download as Markdown | Downloads the report as a `.md` file |
| Collapsible sources | Up to 10 source URLs per message; show/hide toggle |
| Document panel | Right-side drawer to upload, ingest URLs, and delete documents |
| Sidebar history | All past conversations listed with date, template badge, and delete button |
| New Chat button | Clears current thread; starts fresh without losing sidebar history |
| Clickable examples | Welcome screen cards are clickable and set the appropriate template |

---

## System Architecture

```
╔══════════════════════════════════════════════════════════════════════════╗
║                        USER  BROWSER                                    ║
║                                                                          ║
║  ┌─────────────────────────────────────────────────────────────────┐    ║
║  │               Next.js 15  Frontend  (localhost:3000)            │    ║
║  │                                                                  │    ║
║  │  ┌────────────┐  ┌───────────────────────────┐  ┌────────────┐ │    ║
║  │  │  Sidebar   │  │      Chat Interface        │  │  Document  │ │    ║
║  │  │            │  │                            │  │   Panel    │ │    ║
║  │  │ • History  │  │ • Template selector        │  │            │ │    ║
║  │  │ • Sessions │  │ • SSE stream reader        │  │ • Upload   │ │    ║
║  │  │ • Delete   │  │ • Live agent timeline      │  │ • URL      │ │    ║
║  │  │ • Restore  │  │ • Clarification banner     │  │ • List     │ │    ║
║  │  └────────────┘  │ • New Chat button          │  │ • Delete   │ │    ║
║  │                  └───────────────────────────-┘  └────────────┘ │    ║
║  │                                                                  │    ║
║  │  ┌──────────────────────────────────────────────────────────┐   │    ║
║  │  │              MessageBubble component                     │   │    ║
║  │  │  Markdown render · Confidence badge · Sources list       │   │    ║
║  │  │  Copy button · Download .md button                       │   │    ║
║  │  └──────────────────────────────────────────────────────────┘   │    ║
║  └─────────────────────────────────────────────────────────────────┘    ║
║                                                                          ║
║  localStorage: conversations[] (max 20, keyed by thread_id)             ║
╚═══════════════════════════════╦══════════════════════════════════════════╝
                                │  HTTP + Server-Sent Events
                                │  (proxied via Next.js /app/api/* routes)
                                │
╔═══════════════════════════════╩══════════════════════════════════════════╗
║                    FastAPI  Backend  (localhost:8000)                    ║
║                                                                          ║
║  ┌──────────────────────────┐  ┌──────────────────────────────────────┐ ║
║  │     Chat  Endpoints      │  │       Document  Endpoints            │ ║
║  │                          │  │                                      │ ║
║  │  POST /api/chat          │  │  POST   /api/documents/upload        │ ║
║  │  POST /api/chat/stream   │  │  POST   /api/documents/url           │ ║
║  │  GET  /api/health        │  │  GET    /api/documents               │ ║
║  └──────────────────────────┘  │  DELETE /api/documents/{id}          │ ║
║                                └──────────────────────────────────────┘ ║
║                                                                          ║
║  ┌────────────────────────────────────────────────────────────────────┐ ║
║  │              LangGraph  StateGraph  (compiled workflow)            │ ║
║  │                                                                    │ ║
║  │   START ──► Clarity ──► Research ──► [Validator ↔ Research] ──►   │ ║
║  │             Agent        Agent          Agent (retry ≤ 3)         │ ║
║  │                                                         │          │ ║
║  │                                                    Synthesis ──► END│ ║
║  │                                                      Agent          │ ║
║  └────────────────────────────────────────────────────────────────────┘ ║
║                                                                          ║
║  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────────────┐ ║
║  │  Tavily MCP      │  │  Yahoo Finance   │  │  SQLite                │ ║
║  │  (subprocess     │  │  (yfinance)      │  │                        │ ║
║  │   via npx)       │  │                  │  │  clarity_documents.db  │ ║
║  │                  │  │  Real-time:      │  │  └─ FTS5 doc chunks    │ ║
║  │  Web search,     │  │  market cap,     │  │                        │ ║
║  │  news, URLs      │  │  revenue, P/E,   │  │  clarity_checkpoints.db│ ║
║  │  (up to 3 rounds)│  │  margins, EPS    │  │  └─ LangGraph state    │ ║
║  └──────────────────┘  └──────────────────┘  └────────────────────────┘ ║
║                                                                          ║
║  ┌────────────────────────────────────────────────────────────────────┐ ║
║  │                    LLM  Fallback  Chain                            │ ║
║  │                                                                    │ ║
║  │  OpenRouter (LLaMA 3.3 70B) ──► Groq (LLaMA 3.3 70B) ──► Gemini  │ ║
║  │  Primary                        Fast free tier          Fallback  │ ║
║  └────────────────────────────────────────────────────────────────────┘ ║
╚══════════════════════════════════════════════════════════════════════════╝
```

---

## Multi-Agent Pipeline

```
User submits query
        │
        ▼
╔═══════════════════════════════════════════════════════════════╗
║  CLARITY AGENT                                                ║
║                                                               ║
║  Reads: user_query + conversation history (messages[])        ║
║  Model: structured LLM → ClarityOutput (Pydantic)             ║
║                                                               ║
║  Evaluation rules:                                            ║
║  • Single clear company name → CLEAR                          ║
║  • Prior context establishes company → CLEAR                  ║
║  • Ambiguous / no company / too vague → NEEDS_CLARIFICATION   ║
║                                                               ║
║  CLEAR ──────────────────────────────────────────────────────►║
║  NEEDS_CLARIFICATION                                          ║
║    │                                                          ║
║    └──► interrupt() ──► SSE: needs_clarification event        ║
║             │           UI: amber clarification banner         ║
║             │                                                  ║
║         User types answer                                     ║
║             │                                                  ║
║         Command(resume=answer) ──► graph resumes              ║
║         clarity_status = "clear"                              ║
╚═══════════════════════════════════════════════════════════════╝
        │ clarity_status = "clear"
        ▼
╔═══════════════════════════════════════════════════════════════╗
║  RESEARCH AGENT                                               ║
║                                                               ║
║  Step 1 — Financial prefetch                                  ║
║    get_financial_data(query) via yfinance (thread pool)       ║
║    ↳ market cap, revenue, margins, P/E, EPS, growth           ║
║    ↳ appended to LLM prompt if company is publicly traded     ║
║                                                               ║
║  Step 2 — Document search                                     ║
║    search_chunks(query) against SQLite FTS5                   ║
║    ↳ porter-stemmed OR-term matching across all uploaded docs  ║
║    ↳ top-6 matching chunks prepended to LLM prompt            ║
║                                                               ║
║  Step 3 — ReAct web search loop (max 3 rounds)                ║
║    LLM + Tavily MCP tools bound via create_tool_llm()         ║
║    Strategy:                                                  ║
║      • Single company  → overview · recent news · financials  ║
║      • Comparison query → dedicated search per company        ║
║    Source URLs extracted from each tool result (regex)        ║
║                                                               ║
║  Step 4 — Analysis & scoring                                  ║
║    analysis_llm → ResearchOutput (Pydantic)                   ║
║    Fields: research_findings (str), confidence_score (0–10)   ║
║                                                               ║
║  confidence_score ≥ 6 ────────────────────────────────────►  ║
║  confidence_score < 6 ──► VALIDATOR AGENT                     ║
╚═══════════════════════════════════════════════════════════════╝
        │ (only when confidence < 6)
        ▼
╔═══════════════════════════════════════════════════════════════╗
║  VALIDATOR AGENT                                              ║
║                                                               ║
║  Reads: user_query + research_findings + confidence_score     ║
║         + attempts counter                                    ║
║  Model: structured LLM → ValidationOutput (Pydantic)         ║
║  Fields: validation_result, reasoning, missing_aspects[]      ║
║                                                               ║
║  Leniency rule: prefer "sufficient" when findings have        ║
║    reasonable content — avoids infinite retry loops           ║
║                                                               ║
║  SUFFICIENT  ──────────────────────────────────────────────► ║
║  INSUFFICIENT + attempts < 3 ──► back to RESEARCH AGENT       ║
║  INSUFFICIENT + attempts ≥ 3 ──► SYNTHESIS AGENT (forced)     ║
╚═══════════════════════════════════════════════════════════════╝
        │ sufficient OR attempts ≥ 3
        ▼
╔═══════════════════════════════════════════════════════════════╗
║  SYNTHESIS AGENT                                              ║
║                                                               ║
║  Reads: research_findings + confidence_score + sources[]      ║
║         + template + conversation history (last 6 turns)      ║
║  Model: plain LLM (temperature=0)                             ║
║                                                               ║
║  Selects system prompt based on template:                     ║
║    "standard"             → business overview format          ║
║    "investor_memo"        → investment analysis format        ║
║    "competitor_analysis"  → competitive landscape format      ║
║    "swot"                 → four-quadrant SWOT format         ║
║    "comparison"           → side-by-side table + verdict      ║
║                                                               ║
║  Appends ## Sources section if source URLs were collected     ║
║  Writes final_response to state + AIMessage to messages[]     ║
╚═══════════════════════════════════════════════════════════════╝
        │
        ▼
  Final response streamed
  to frontend via SSE "final" event
        │
        ▼
  Saved to localStorage conversation history
```

---

## Agent Reference

### Clarity Agent (`agents/clarity_agent.py`)

| Property | Value |
|---|---|
| Input | `user_query`, `messages[]` (history) |
| Output type | `ClarityOutput` (Pydantic) |
| Output fields | `clarity_status: Literal["clear", "needs_clarification"]`, `clarification_question: Optional[str]` |
| LLM call | `create_structured_llm(ClarityOutput)` |
| Special behaviour | Calls `interrupt()` on ambiguous queries — pauses the graph mid-execution until the user responds |
| Resume path | `Command(resume=clarification_text)` resumes at the same node; `clarity_status` is set to `"clear"` |

**Clarity rules:**

- A named company (`Tesla`, `OpenAI`, `Apple Inc.`) → **clear**
- Follow-up using pronouns when a company is established in history (`"What about their competitors?"`) → **clear**
- Generic request with no company (`"Tell me about tech companies"`) → **needs_clarification**
- Genuinely ambiguous name without context (`"Apple"` could be Apple Inc. or Apple Corps) → **needs_clarification**

---

### Research Agent (`agents/research_agent.py`)

| Property | Value |
|---|---|
| Input | `clarified_query`, `messages[]`, `template` |
| Output fields | `research_findings: str`, `confidence_score: int (0–10)`, `attempts: int`, `sources: List[str]` |
| Tool loop | ReAct via `create_tool_llm(search_tools)` — Tavily only (financial tool called separately) |
| Max search rounds | 3 |
| Max findings chars | 4 000 (passed to analysis LLM) |
| Max tool result chars | 3 000 per result (TPM budget control) |

**Three-phase execution:**

```
Phase 1 · Financial prefetch
  get_financial_data(query)  ← yfinance, runs in thread pool
  Result prepended to LLM prompt as "## Real-Time Financial Data"

Phase 2 · Document search
  search_chunks(query, limit=6)  ← SQLite FTS5
  Porter-stemmed OR-term query against all uploaded doc chunks
  Matching chunks prepended as "## Context from Uploaded Documents"

Phase 3 · Web search loop
  LLM with Tavily tools  ← up to 3 iterations
  For single company: overview → recent news → financials
  For comparison query: one search per company
  Source URLs extracted from every tool result (regex: https?://...)
```

---

### Validator Agent (`agents/validator_agent.py`)

| Property | Value |
|---|---|
| Input | `user_query`, `research_findings`, `confidence_score`, `attempts` |
| Output type | `ValidationOutput` (Pydantic) |
| Output fields | `validation_result: Literal["sufficient", "insufficient"]`, `reasoning: str`, `missing_aspects: List[str]` |
| Retry cap | 3 attempts total (enforced by `_route_after_validator`) |
| Design intent | Leniency-biased — only marks insufficient when findings are genuinely too sparse to be useful |

---

### Synthesis Agent (`agents/synthesis_agent.py`)

| Property | Value |
|---|---|
| Input | `research_findings`, `confidence_score`, `sources`, `template`, `messages[]` |
| Output | `final_response: str` (Markdown), `messages[]` (appends `AIMessage`) |
| History window | Last 6 messages (bounded to control token spend) |
| Sources | Appended as `## Sources` section when `sources[]` is non-empty |
| Temperature | 0 (deterministic, factual output) |

---

## LLM Fallback Chain

All agents share a single provider abstraction in `llm/provider.py`. Providers are tried in priority order; if one raises an error (rate limit, quota, etc.) the next is tried automatically via LangChain's `with_fallbacks()`.

```
┌──────────────────────────────────────────────────────────────────────┐
│                      Provider Priority Order                         │
│                                                                      │
│  1. OpenRouter  ──  meta-llama/llama-3.3-70b-instruct:free           │
│     • Env var:  OPENROUTER_API_KEY                                   │
│     • Headers:  HTTP-Referer, X-Title forwarded                      │
│     • max_retries = 0 (fail fast, let fallback chain handle 429s)    │
│                                                                      │
│  2. Groq  ──  llama-3.3-70b-versatile                                │
│     • Env var:  GROQ_API_KEY                                         │
│     • Very fast inference; free tier ~12 000 TPM                     │
│                                                                      │
│  3. Google Gemini  ──  gemini-2.0-flash                              │
│     • Env var:  GOOGLE_API_KEY                                       │
│     • max_retries = 0                                                │
│                                                                      │
│  Only providers whose API key is present are included.               │
│  LLM_PROVIDERS=groq  forces Groq-only (useful during rate limits).   │
└──────────────────────────────────────────────────────────────────────┘

                          create_llm()
                       ┌──────────────┐
              plain    │  primary     │
              chat  ◄──│  .with_      │◄── _build_providers(temperature)
                       │  fallbacks() │
                       └──────────────┘

                     create_structured_llm(Schema)
                       ┌──────────────────────────┐
           structured  │  Each provider wrapped   │
           output   ◄──│  with .with_structured_  │
                       │  output(Schema) before   │
                       │  fallback chain is built │
                       └──────────────────────────┘

                        create_tool_llm(tools)
                       ┌──────────────────────────┐
              tool      │  Each provider wrapped   │
              calling◄──│  with .bind_tools(tools) │
                        │  before fallback chain   │
                        └──────────────────────────┘
```

Model defaults are overridable via environment variables:

| Variable | Default |
|---|---|
| `OPENROUTER_MODEL` | `meta-llama/llama-3.3-70b-instruct:free` |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` |
| `GEMINI_MODEL` | `gemini-2.0-flash` |

---

## Research Data Sources

```
┌──────────────────────────────────────────────────────────────────────┐
│               Research Agent — Three Data Sources                    │
│                                                                      │
│  ┌─────────────────────┐                                             │
│  │  1. Yahoo Finance   │  Always queried first (proactively)         │
│  │     (yfinance)      │  Runs in asyncio thread pool to avoid       │
│  │                     │  blocking the event loop                    │
│  │  Returns:           │  Falls back gracefully for private co's     │
│  │  • Stock price      │                                             │
│  │  • Market cap       │  Output format:                             │
│  │  • Revenue (TTM)    │  "## Real-Time Financial Data               │
│  │  • Net income       │   **NVIDIA** (NVDA)                         │
│  │  • Gross margin     │   Sector: Technology                        │
│  │  • Operating margin │   Market Cap: $3.18T                        │
│  │  • P/E ratio        │   Annual Revenue: $130.50B                  │
│  │  • Forward P/E      │   ..."                                      │
│  │  • EPS (TTM)        │                                             │
│  │  • Revenue growth   │                                             │
│  │  • 52-week range    │                                             │
│  │  • Employees        │                                             │
│  │  • Cash & debt      │                                             │
│  └─────────────────────┘                                             │
│                                                                      │
│  ┌─────────────────────┐                                             │
│  │  2. Document Store  │  Queried second (if docs are uploaded)      │
│  │     (SQLite FTS5)   │  Porter-stemmed full-text search            │
│  │                     │  Returns top-6 most relevant chunks         │
│  │  Accepts:           │  Each chunk ≤ 700 words (80-word overlap)   │
│  │  • PDF files        │                                             │
│  │  • .txt files       │  Output format:                             │
│  │  • Web page URLs    │  "## Context from Uploaded Documents        │
│  │                     │   [annual-report-2024.pdf]:                 │
│  │  Persists across    │   ...chunk text..."                         │
│  │  server restarts    │                                             │
│  └─────────────────────┘                                             │
│                                                                      │
│  ┌─────────────────────┐                                             │
│  │  3. Tavily MCP      │  Web search via MCP stdio transport         │
│  │     (live web)      │  Spawned as npx subprocess on startup       │
│  │                     │  LLM decides search queries (ReAct)         │
│  │  Up to 3 rounds:    │                                             │
│  │  • Company overview │  Source URLs extracted via regex            │
│  │  • Recent news      │  and surfaced in the UI under each message  │
│  │  • Financials /     │                                             │
│  │    market position  │                                             │
│  └─────────────────────┘                                             │
│                                                                      │
│  All three results are merged before the analysis LLM runs.          │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Document Ingestion Pipeline

```
User uploads PDF / .txt / URL
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│  POST /api/documents/upload   or   POST /api/documents/url       │
│                                                                  │
│  PDF path:                          URL path:                    │
│  pypdf.PdfReader → extract text     httpx GET (20s timeout)      │
│  per page → join with "\n\n"        → HTML → _TextStripper       │
│                                     (skips script/style/nav)     │
│  .txt path:                         → plain text                 │
│  utf-8 decode (errors=replace)                                   │
└──────────────────────────────────────────────────────────────────┘
           │  raw text (str)
           ▼
┌──────────────────────────────────────────────────────────────────┐
│  _chunk_text(text, chunk_size=700, overlap=80)                   │
│                                                                  │
│  Splits on whitespace into word-count windows:                   │
│                                                                  │
│  Chunk 0:  words[0   : 700]                                      │
│  Chunk 1:  words[620 : 1320]   ← 80-word overlap with chunk 0   │
│  Chunk 2:  words[1240: 1940]   ← 80-word overlap with chunk 1   │
│  ...                                                             │
│                                                                  │
│  Overlap prevents splitting concepts across boundaries           │
└──────────────────────────────────────────────────────────────────┘
           │  chunks: List[str]
           ▼
┌──────────────────────────────────────────────────────────────────┐
│  SQLite  clarity_documents.db                                    │
│                                                                  │
│  doc_chunks (FTS5 virtual table)                                 │
│  ┌──────────┬──────────────────┬──────────────────────────────┐  │
│  │ doc_id   │ filename         │ content (FTS5 indexed)        │  │
│  │ (uuid)   │ annual-rep.pdf   │ "During fiscal year 2024..."  │  │
│  │ (uuid)   │ annual-rep.pdf   │ "Revenue grew 122% YoY..."    │  │
│  └──────────┴──────────────────┴──────────────────────────────┘  │
│                                                                  │
│  documents (metadata table)                                      │
│  ┌──────────┬────────────────┬─────────────┬────────────────┐   │
│  │ id       │ filename       │ source_type │ chunk_count    │   │
│  │ (uuid)   │ annual-rep.pdf │ pdf         │ 42             │   │
│  └──────────┴────────────────┴─────────────┴────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
           │
           ▼ (at research time)
┌──────────────────────────────────────────────────────────────────┐
│  search_chunks(query, limit=6)                                   │
│                                                                  │
│  1. Strip punctuation from query                                 │
│  2. Remove stop words; take first 10 terms                       │
│  3. Build FTS5 OR-query: "NVIDIA OR revenue OR strategy OR ..."  │
│  4. Execute: WHERE doc_chunks MATCH ? ORDER BY rank LIMIT 6      │
│  5. Return list of {doc_id, filename, content} dicts             │
└──────────────────────────────────────────────────────────────────┘
```

---

## State Management & Persistence

### AgentState fields

```python
class AgentState(TypedDict):
    messages:          Annotated[List[BaseMessage], add_messages]
    user_query:        str
    clarified_query:   Optional[str]
    clarity_status:    Optional[str]
    research_findings: Optional[str]
    confidence_score:  Optional[int]
    validation_result: Optional[str]
    attempts:          int
    final_response:    Optional[str]
    template:          Optional[str]   # report format selector
    sources:           Optional[List[str]]  # source URLs from Tavily
```

**`add_messages` reducer** — the `messages` field uses a custom reducer that appends new messages instead of overwriting. This is what enables multi-turn memory: every agent can read the full conversation history without receiving the entire state as input.

### Persistence layer

```
Request arrives with thread_id = "abc123"
         │
         ▼
graph.get_state({"configurable": {"thread_id": "abc123"}})
         │
         ├── state.next is set?
         │     YES → graph is paused (interrupt) → resume with Command
         │     NO  → start fresh with _build_initial_state()
         │
         ▼
Graph runs → each node writes output back to state
         │
         ▼
AsyncSqliteSaver persists checkpoint after each node
    clarity_checkpoints.db
    └── table: checkpoints
        key: thread_id + checkpoint_ns + checkpoint_id
        value: serialized AgentState blob
         │
         ▼
Server restarts → same thread_id → state restored from DB
```

### Checkpointer selection

```
App startup
    │
    ├── langgraph-checkpoint-sqlite installed?
    │     YES → AsyncSqliteSaver("clarity_checkpoints.db")
    │           Conversations persist across restarts ✓
    │
    └── NO  → MemorySaver()  (fallback)
              Conversations lost on restart
              Warning logged to console
```

---

## SSE Streaming Flow

```
Frontend                    Next.js proxy            FastAPI backend
   │                             │                        │
   │  fetch POST /api/chat/stream│                        │
   │ ─────────────────────────►  │                        │
   │                             │  fetch POST            │
   │                             │ ───────────────────►   │
   │                             │                        │  graph.astream_events()
   │                             │                        │  version="v2"
   │                             │                        │  │
   │                             │                        │  ▼ on_chain_start "clarity"
   │   data: {"type":"agent_start","agent":"Clarity Agent"}│
   │ ◄─────────────────────────────────────────────────── │
   │                             │                        │  ▼ on_chain_end "clarity"
   │   data: {"type":"agent_end","agent":"Clarity Agent","output":{}}
   │ ◄─────────────────────────────────────────────────── │
   │                             │                        │  ▼ on_chain_start "research"
   │   data: {"type":"agent_start","agent":"Research Agent"}
   │ ◄─────────────────────────────────────────────────── │
   │                             │                        │  ... (tool calls happen)
   │   data: {"type":"agent_end","agent":"Research Agent","output":{"confidence_score":8}}
   │ ◄─────────────────────────────────────────────────── │
   │                             │                        │  ▼ on_chain_start "synthesis"
   │   data: {"type":"agent_start","agent":"Synthesis Agent"}
   │ ◄─────────────────────────────────────────────────── │
   │   data: {"type":"agent_end",...}                     │
   │ ◄─────────────────────────────────────────────────── │
   │                             │                        │  stream ends
   │                             │                        │  graph.get_state() → final values
   │   data: {"type":"final","response":"## Company...","confidence_score":8,"sources":[...]}
   │ ◄─────────────────────────────────────────────────── │
   │   data: [DONE]              │                        │
   │ ◄─────────────────────────────────────────────────── │
   │                             │                        │
   UI updates:
   • Agent timeline: each step running → completed
   • Final message rendered with Markdown
   • Confidence badge shown
   • Sources list appended
   • Saved to localStorage
```

**Clarification interrupt path:**

```
   ...after Clarity Agent runs interrupt()...

   data: {"type":"needs_clarification","question":"Which company?","thread_id":"abc"}
   UI: amber banner appears, input placeholder changes to "Type your clarification…"

   User types answer → POST /api/chat/stream with same thread_id
   Backend: graph.get_state() shows state.next → Command(resume=answer) sent
   Graph resumes from interrupt point → continues to Research Agent
```

---

## Report Templates

Each template selects a different system prompt for the Synthesis Agent.

| Template ID | Format produced |
|---|---|
| `standard` | Company Overview · Recent Developments · Financial Insights · Risks & Opportunities · Key Takeaways |
| `investor_memo` | Executive Summary · Company Overview · Investment Thesis · Financial Highlights · Market Opportunity · Key Risks · Management & Strategy · Conclusion |
| `competitor_analysis` | Company Overview · Competitive Landscape · Key Competitors · Competitive Advantages · Competitive Weaknesses · Market Position · Strategic Opportunities & Threats · Competitive Verdict |
| `swot` | Company Overview · Strengths · Weaknesses · Opportunities · Threats · Strategic Summary |
| `comparison` | Overview · At a Glance (table) · Recent Developments · Financial Comparison · Competitive Positioning · Strengths & Weaknesses · Key Differences · Verdict |

Templates are passed in the `template` field of every request body and stored in `AgentState`.

---

## Frontend Architecture

```
app/
├── page.tsx                     Entry point — renders <ChatInterface />
├── layout.tsx                   Root layout + metadata
├── globals.css                  Tailwind base + prose-chat styles + scrollbar
└── api/                         Next.js API routes (proxy to backend)
    ├── chat/route.ts             POST /api/chat
    ├── chat/stream/route.ts      POST /api/chat/stream  (SSE passthrough)
    └── documents/
        ├── route.ts              GET /api/documents
        ├── upload/route.ts       POST /api/documents/upload (multipart)
        ├── url/route.ts          POST /api/documents/url
        └── [id]/route.ts         DELETE /api/documents/{id}

components/
├── ChatInterface.tsx            ┐
│   • State: messages, threadId  │
│   • State: selectedTemplate    │
│   • State: sidebarOpen         │  Main application shell
│   • State: documentsOpen       │
│   • State: conversations[]     │
│   • sendMessage() → SSE reader │
│   • saveConversation() → LS    ┘
│
├── Sidebar.tsx                  Conversation history drawer (left)
│   • Lists conversations from localStorage
│   • Click to restore; delete per entry
│   • New Chat button
│
├── DocumentPanel.tsx            Document management drawer (right, fixed overlay)
│   • File upload (PDF / .txt)
│   • URL ingestion
│   • Document list with delete
│
├── MessageBubble.tsx            Per-message renderer
│   • User messages: right-aligned, brand color
│   • Assistant messages:
│       - Markdown via react-markdown + remark-gfm
│       - Hover-reveal: Copy button + Download .md button
│       - Confidence badge (color-coded)
│       - Collapsible sources list (show 3, expand for more)
│   • Agent timeline shown above assistant messages
│
├── AgentTimeline.tsx            Live + historical agent step list
│   • Status icons: ○ pending · ◌ running (pulse) · ✓ completed · ✗ error
│   • Inline detail: confidence score, clarity status, validation result
│
types/
└── index.ts                     TypeScript interfaces
    • AgentStep, ChatMessage, Conversation
    • SSEEvent, StoredDocument
    • TemplateId, TemplateOption, TEMPLATES[]
```

### localStorage schema

```typescript
// Key: "clarityai_conversations"
// Value: JSON array, max 20 entries, newest first

Conversation {
  id:          string     // = threadId
  title:       string     // first user message, max 55 chars
  messages:    ChatMessage[]
  threadId:    string
  template:    string     // template used for this session
  createdAt:   string     // ISO 8601
}
```

---

## Tech Stack

### Backend

| Layer | Technology | Purpose |
|---|---|---|
| Web framework | FastAPI 0.115+ | Async HTTP server, SSE streaming |
| Agent orchestration | LangGraph 0.2.57+ | StateGraph, interrupt, checkpointing |
| LLM abstraction | LangChain 0.3+ | Provider wrappers, tool binding, structured output |
| LLM providers | OpenRouter / Groq / Gemini | Three-tier fallback chain |
| Web search | Tavily MCP (`tavily-mcp` via npx) | Real-time web search as MCP tool |
| Financial data | yfinance 0.2.44+ | Yahoo Finance market data |
| Document parsing | pypdf 4.0+ | PDF text extraction |
| Document store | SQLite FTS5 + aiosqlite | Full-text search over uploaded docs |
| State persistence | langgraph-checkpoint-sqlite | SQLite-backed conversation checkpoints |
| HTTP client | httpx 0.27+ | Async URL fetching for document ingestion |
| Validation | Pydantic 2.10+ | Structured agent outputs, request models |
| Environment | python-dotenv | `.env` file loading |

### Frontend

| Layer | Technology | Purpose |
|---|---|---|
| Framework | Next.js 15 (App Router) | React SSR, API routes as backend proxy |
| Language | TypeScript 5.5+ | Full type safety |
| Styling | Tailwind CSS 3.4 | Utility-first styling |
| Markdown | react-markdown + remark-gfm | Renders agent reports with GFM tables |
| ID generation | uuid v10 | Thread IDs, message IDs |
| Persistence | localStorage | Conversation history, no backend needed |

---

## Project Structure

```
ClarityAI/
│
├── backend/
│   ├── agents/
│   │   ├── clarity_agent.py       ClarityOutput pydantic model + interrupt logic
│   │   ├── research_agent.py      Financial prefetch + doc search + ReAct web loop
│   │   ├── validator_agent.py     ValidationOutput + retry routing
│   │   └── synthesis_agent.py     5 template prompts + Sources section
│   │
│   ├── graph/
│   │   ├── state.py               AgentState TypedDict (add_messages reducer)
│   │   └── workflow.py            StateGraph compilation + conditional edges
│   │
│   ├── tools/
│   │   ├── tavily_mcp.py          MultiServerMCPClient setup (stdio transport)
│   │   └── financial.py           get_financial_data async LangChain tool
│   │
│   ├── documents/
│   │   ├── __init__.py
│   │   └── store.py               init_db, store_document, search_chunks,
│   │                              list_documents, delete_document
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   └── provider.py            _build_providers, create_llm,
│   │                              create_structured_llm, create_tool_llm
│   │
│   ├── api/
│   │   ├── __init__.py            Shared app_state dict
│   │   ├── routes.py              /chat, /chat/stream, /health
│   │   └── document_routes.py     /documents CRUD + URL ingestion
│   │
│   ├── main.py                    FastAPI app + lifespan (MCP + checkpointer + doc init)
│   ├── requirements.txt
│   ├── .env.example
│   ├── clarity_checkpoints.db     Auto-created: LangGraph thread state (SQLite)
│   └── clarity_documents.db       Auto-created: Document chunks FTS5 (SQLite)
│
└── frontend/
    ├── app/
    │   ├── page.tsx               Root page — renders <ChatInterface />
    │   ├── layout.tsx             HTML shell + metadata
    │   ├── globals.css            Tailwind + prose-chat + scrollbar styles
    │   └── api/
    │       ├── chat/route.ts      Proxy: POST /api/chat
    │       ├── chat/stream/       Proxy: POST /api/chat/stream (SSE passthrough)
    │       │   └── route.ts
    │       └── documents/
    │           ├── route.ts       Proxy: GET /api/documents
    │           ├── upload/        Proxy: POST /api/documents/upload
    │           │   └── route.ts
    │           ├── url/           Proxy: POST /api/documents/url
    │           │   └── route.ts
    │           └── [id]/          Proxy: DELETE /api/documents/{id}
    │               └── route.ts
    │
    ├── components/
    │   ├── ChatInterface.tsx      Main shell: state, SSE, localStorage, layout
    │   ├── MessageBubble.tsx      Message render + copy + download + sources
    │   ├── AgentTimeline.tsx      Step-by-step agent activity list
    │   ├── Sidebar.tsx            Conversation history drawer
    │   └── DocumentPanel.tsx      Document upload/ingest/list drawer
    │
    ├── types/
    │   └── index.ts               All shared TypeScript types + TEMPLATES constant
    │
    ├── package.json
    ├── tailwind.config.ts
    ├── tsconfig.json
    └── next.config.ts
```

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | Required for `asyncio` features and type hints used |
| Node.js | 18+ | Required to run `npx tavily-mcp` (spawned by backend) |
| npm / npx | bundled with Node.js | No global install needed; `npx -y` downloads on first run |

---

## Setup & Running

### 1. Clone and enter the project

```bash
git clone <your-repo-url>
cd ClarityAI
```

### 2. Backend

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

# Install all dependencies
pip install -r requirements.txt

# Create your .env file
copy .env.example .env        # Windows
cp .env.example .env          # macOS / Linux

# Edit .env and add your API keys (see Environment Variables section)
```

Start the backend:

```bash
python main.py
```

The backend starts at **http://localhost:8000**. On startup it will:

1. Validate that at least one LLM key and `TAVILY_API_KEY` are set
2. Initialise `clarity_documents.db` (SQLite FTS5 — created if missing)
3. Attempt to open `clarity_checkpoints.db` via `AsyncSqliteSaver`
4. Spawn the Tavily MCP server as an `npx` subprocess
5. Load MCP tool wrappers via `langchain_mcp_adapters`
6. Add the `get_financial_data` tool alongside MCP tools
7. Compile the LangGraph StateGraph workflow

### 3. Frontend

```bash
cd frontend

npm install

npm run dev
```

The frontend starts at **http://localhost:3000**.

---

## Environment Variables

Create `backend/.env` from `backend/.env.example`:

```dotenv
# ── LLM Providers (at least one required) ────────────────────────────────────
# Priority order: OpenRouter → Groq → Gemini

# 1. OpenRouter — https://openrouter.ai/keys
OPENROUTER_API_KEY=your_key_here
# OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct:free   # default (free tier)

# 2. Groq — https://console.groq.com
GROQ_API_KEY=your_key_here
# GROQ_MODEL=llama-3.3-70b-versatile                        # default

# 3. Google Gemini — https://aistudio.google.com/app/apikey
GOOGLE_API_KEY=your_key_here
# GEMINI_MODEL=gemini-2.0-flash                             # default

# ── Search (required) ────────────────────────────────────────────────────────
TAVILY_API_KEY=your_key_here   # https://app.tavily.com

# ── Optional overrides ───────────────────────────────────────────────────────
# LLM_PROVIDERS=groq            # Force a single provider (useful when others rate-limit)
```

Frontend environment (optional — create `frontend/.env.local`):

```dotenv
BACKEND_URL=http://localhost:8000   # default; override if backend runs elsewhere
```

---

## API Reference

### `POST /api/chat`

Standard request/response. Waits for the full pipeline to complete.

**Request body:**
```json
{
  "message": "Research NVIDIA's AI strategy",
  "thread_id": "optional-uuid-for-follow-ups",
  "template": "standard"
}
```

`template` values: `standard` · `investor_memo` · `competitor_analysis` · `swot` · `comparison`

**Response — success:**
```json
{
  "status": "success",
  "response": "## Company Overview\n...",
  "confidence_score": 8,
  "sources": ["https://...", "https://..."],
  "thread_id": "abc-123"
}
```

**Response — clarification needed:**
```json
{
  "status": "needs_clarification",
  "question": "Which company are you referring to?",
  "thread_id": "abc-123"
}
```

To resume: send another POST with the **same `thread_id`** and the clarification as `message`.

---

### `POST /api/chat/stream`

SSE streaming endpoint. Emits agent lifecycle events so the UI can render a live timeline.

**Request body:** same as `/api/chat`

**Event stream:**
```
data: {"type": "agent_start",         "agent": "Clarity Agent",   "thread_id": "abc"}
data: {"type": "agent_end",           "agent": "Clarity Agent",   "output": {"clarity_status": "clear"}}
data: {"type": "agent_start",         "agent": "Research Agent",  "thread_id": "abc"}
data: {"type": "agent_end",           "agent": "Research Agent",  "output": {"confidence_score": 8}}
data: {"type": "agent_start",         "agent": "Synthesis Agent", "thread_id": "abc"}
data: {"type": "agent_end",           "agent": "Synthesis Agent", "output": {}}
data: {"type": "final",               "response": "## ...",       "confidence_score": 8,
       "sources": ["https://..."],    "thread_id": "abc"}
data: [DONE]
```

**Clarification path:**
```
data: {"type": "needs_clarification", "question": "...", "thread_id": "abc"}
data: [DONE]
```

**Error:**
```
data: {"type": "error", "message": "..."}
data: [DONE]
```

---

### `GET /api/health`

Returns runtime status.

**Response:**
```json
{
  "status": "ok",
  "tools_loaded": true,
  "tools": ["tavily_search", "get_financial_data"],
  "llm_providers": ["Groq"]
}
```

---

### `POST /api/documents/upload`

Upload a PDF or plain-text file. `multipart/form-data`.

**Form field:** `file` (PDF or `.txt`)

**Response:**
```json
{
  "id": "uuid",
  "filename": "annual-report-2024.pdf",
  "source_type": "pdf",
  "chunk_count": 42
}
```

---

### `POST /api/documents/url`

Fetch and index a public web page.

**Request body:**
```json
{
  "url": "https://example.com/press-release",
  "label": "optional display name"
}
```

**Response:** same shape as `/upload`

---

### `GET /api/documents`

List all indexed documents.

**Response:**
```json
{
  "documents": [
    {
      "id": "uuid",
      "filename": "annual-report-2024.pdf",
      "source_type": "pdf",
      "chunk_count": 42,
      "uploaded_at": "2025-06-10T12:00:00"
    }
  ]
}
```

---

### `DELETE /api/documents/{id}`

Remove a document and all its chunks from the index.

**Response:**
```json
{ "ok": true }
```

---

## Multi-Turn Conversation

The same `thread_id` maintains conversation history across requests. Each agent receives the full `messages[]` list, so pronouns and references are understood:

```
Turn 1: { "message": "Research OpenAI",               "thread_id": null   }
         → thread_id "abc" created and returned

Turn 2: { "message": "What about their competitors?",  "thread_id": "abc"  }
         → Clarity Agent sees "OpenAI" in history → CLEAR (no interruption)
         → Research Agent context: "Conversation context: User: Research OpenAI..."

Turn 3: { "message": "Focus on funding rounds",        "thread_id": "abc"  }
         → Still in OpenAI context; synthesis focuses on funding

Turn 4: { "message": "Now research Anthropic",         "thread_id": "abc"  }
         → New query on same thread; full history preserved
```

When the same thread is used for a new query after the previous one completed, `_build_initial_state()` is called — the state fields reset but the `messages[]` history is preserved by the `add_messages` reducer.

---

## Technical Design Decisions

### `add_messages` reducer instead of state overwrite

LangGraph nodes typically overwrite state fields. Using `Annotated[List[BaseMessage], add_messages]` causes new messages to be appended rather than replaced. This is what enables genuine multi-turn memory: each agent reads the complete conversation history without any field being clobbered mid-pipeline.

### `interrupt()` for human-in-the-loop

When the Clarity Agent calls `interrupt({"question": "..."})`, LangGraph checkpoints the graph mid-node and raises an exception that the framework catches. The graph is now in a "paused" state readable via `graph.get_state()`. The client detects `state.next` being non-empty and renders the clarification UI. When the user responds, `Command(resume=text)` restores execution from the exact checkpoint.

### Structured outputs via Pydantic + `.with_structured_output()`

Every routing decision uses a Pydantic model (not free-form text parsing):

- `ClarityOutput` → `clarity_status: Literal["clear", "needs_clarification"]`
- `ResearchOutput` → `research_findings: str`, `confidence_score: int`
- `ValidationOutput` → `validation_result: Literal["sufficient", "insufficient"]`

This eliminates the fragility of parsing LLM text to make routing decisions.

### Financial data called proactively, not as LLM tool

The `get_financial_data` tool is bound to `tools_by_name` but deliberately excluded from the LLM's tool-calling loop. It is always invoked first, before any web search. This guarantees that every report for a publicly traded company includes real numbers regardless of whether the LLM would have decided to call it.

### Separate search tools from financial tool at the boundary

```python
search_tools = [t for t in tools if t.name != "get_financial_data"]
llm_with_tools = create_tool_llm(search_tools, temperature=0.1)
```

This prevents the LLM from calling `get_financial_data` a second time inside the ReAct loop (wasting tokens on duplicate data).

### SQLite FTS5 porter tokenizer for document search

Porter stemming means searching for `"researching"` matches chunks containing `"research"`, `"researcher"`, etc. This dramatically improves recall for business documents where variations of the same term are common.

### yfinance in `asyncio.run_in_executor`

`yfinance.Ticker.info` makes synchronous HTTP requests internally. Calling it directly in an `async` function would block FastAPI's event loop. Wrapping it in `loop.run_in_executor(None, _fetch_sync, query)` pushes it to a thread pool, keeping the event loop free.

### SSE via `graph.astream_events(version="v2")`

LangGraph's `astream_events` emits fine-grained lifecycle events (`on_chain_start`, `on_chain_end`) for every node. Filtering by `node_name in AGENT_DISPLAY_NAMES` selects only the four named agent nodes, ignoring internal LangGraph infrastructure events. This keeps the event stream clean and predictable for the frontend.

### Confidence threshold at 6 (not 5 or 7)

The routing condition `confidence_score >= 6` was chosen to allow scores of 6 ("adequate for basic research, some key areas missing") to bypass the validator. This reduces unnecessary LLM calls for queries where Tavily returns reasonable but not perfect data. The validator still catches any score below 6 and can trigger a retry.

### TPM budget control via `MAX_TOOL_RESULT_CHARS = 3000`

Tavily results are truncated to 3 000 characters before being added to the LLM context. With up to 3 tool calls and a 12 000 TPM free tier (Groq), this leaves headroom for the system prompt, query, and history without hitting rate limits mid-pipeline.
