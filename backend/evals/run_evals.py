"""
ClarityAI Evaluation Suite
Run with: python -m evals.run_evals [--url http://localhost:8000] [--case <id>] [--out results.json]

Requires the backend to be running. Tests each case against the live API
and scores the response against declared criteria.
"""

import argparse
import asyncio
import json
import re
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

CASES_FILE = Path(__file__).parent / "cases.json"

# ── Scoring ───────────────────────────────────────────────────────────────────

def _score(response: str, confidence: int, sources: list, criteria: dict) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    notes: list[str] = []

    # Word count
    word_count = len(response.split())
    min_words = criteria.get("min_words", 0)
    checks["min_words"] = word_count >= min_words
    if not checks["min_words"]:
        notes.append(f"Only {word_count} words (need {min_words})")

    # Confidence score range
    min_conf = criteria.get("min_confidence", 0)
    max_conf = criteria.get("confidence_max", 10)
    checks["confidence_score"] = min_conf <= confidence <= max_conf
    if not checks["confidence_score"]:
        notes.append(f"Confidence {confidence} outside [{min_conf}, {max_conf}]")

    # Required keywords
    response_lower = response.lower()
    must_mention = criteria.get("must_mention", [])
    for term in must_mention:
        ok = term.lower() in response_lower
        checks[f"mentions_{term.lower().replace(' ', '_')}"] = ok
        if not ok:
            notes.append(f"Missing expected term: '{term}'")

    # Required section headers
    required_sections = criteria.get("required_sections", [])
    for section in required_sections:
        ok = section.lower() in response_lower
        checks[f"section_{section.lower().replace(' ', '_')}"] = ok
        if not ok:
            notes.append(f"Missing expected section: '{section}'")

    # Forbidden phrases
    must_not_contain = criteria.get("must_not_contain", [])
    for phrase in must_not_contain:
        found = phrase.lower() in response_lower
        checks[f"no_{phrase[:20].lower().replace(' ', '_')}"] = not found
        if found:
            notes.append(f"Response contains forbidden phrase: '{phrase}'")

    # Sources
    if criteria.get("must_have_sources"):
        checks["has_sources"] = len(sources) > 0
        if not checks["has_sources"]:
            notes.append("No source URLs returned")

    # Financial figures (optional regex check)
    pattern = criteria.get("financial_figures_pattern")
    if pattern:
        checks["has_financial_figures"] = bool(re.search(pattern, response))
        if not checks["has_financial_figures"]:
            notes.append("No financial figures (e.g. $X) found in response")

    passed = sum(1 for v in checks.values() if v)
    total = len(checks)
    score = round(passed / total * 100, 1) if total else 100.0

    return {
        "checks": checks,
        "passed": passed,
        "total": total,
        "score_pct": score,
        "notes": notes,
    }


# ── API call ──────────────────────────────────────────────────────────────────

async def _run_case(client: httpx.AsyncClient, base_url: str, case: dict) -> dict:
    thread_id = str(uuid.uuid4())
    payload = {
        "message": case["message"],
        "template": case.get("template", "standard"),
        "thread_id": thread_id,
    }

    start = time.monotonic()
    try:
        resp = await client.post(
            f"{base_url}/api/chat",
            json=payload,
            timeout=120.0,
        )
        elapsed = round(time.monotonic() - start, 2)

        if resp.status_code != 200:
            return {
                "id": case["id"],
                "status": "api_error",
                "http_status": resp.status_code,
                "body": resp.text[:300],
                "elapsed_s": elapsed,
            }

        data = resp.json()

        if data.get("status") == "needs_clarification":
            return {
                "id": case["id"],
                "status": "needs_clarification",
                "question": data.get("question"),
                "elapsed_s": elapsed,
                "score_pct": 0,
                "notes": ["Graph interrupted for clarification — ambiguous query"],
            }

        response_text = data.get("response", "")
        confidence = int(data.get("confidence_score") or 0)
        sources = data.get("sources") or []

        result = _score(response_text, confidence, sources, case["criteria"])
        return {
            "id": case["id"],
            "description": case["description"],
            "status": "pass" if result["score_pct"] == 100.0 else "fail",
            "score_pct": result["score_pct"],
            "passed_checks": result["passed"],
            "total_checks": result["total"],
            "confidence_score": confidence,
            "source_count": len(sources),
            "word_count": len(response_text.split()),
            "elapsed_s": elapsed,
            "checks": result["checks"],
            "notes": result["notes"],
        }

    except httpx.TimeoutException:
        return {
            "id": case["id"],
            "status": "timeout",
            "elapsed_s": round(time.monotonic() - start, 2),
            "score_pct": 0,
            "notes": ["Request timed out after 120s"],
        }
    except Exception as exc:
        return {
            "id": case["id"],
            "status": "error",
            "error": str(exc),
            "elapsed_s": round(time.monotonic() - start, 2),
            "score_pct": 0,
            "notes": [str(exc)],
        }


# ── Runner ────────────────────────────────────────────────────────────────────

def _print_result(r: dict, idx: int, total: int) -> None:
    status_icon = {"pass": "PASS", "fail": "FAIL", "timeout": "TIMEOUT", "error": "ERROR", "api_error": "ERROR", "needs_clarification": "CLARIFY"}.get(r.get("status", ""), "???")
    score = r.get("score_pct", 0)
    elapsed = r.get("elapsed_s", 0)
    notes = r.get("notes", [])

    print(f"  [{idx:2}/{total}] {status_icon:<8} {r['id']:<40} {score:5.1f}%  {elapsed:6.1f}s")
    for note in notes:
        print(f"               > {note}")


async def run(base_url: str, filter_id: str | None, out_path: str | None) -> None:
    cases = json.loads(CASES_FILE.read_text())

    if filter_id:
        cases = [c for c in cases if c["id"] == filter_id]
        if not cases:
            print(f"No case found with id '{filter_id}'")
            sys.exit(1)

    # Health check
    async with httpx.AsyncClient() as client:
        try:
            health = await client.get(f"{base_url}/api/health", timeout=5.0)
            health_data = health.json()
            print(f"\nClarityAI Eval Suite — {base_url}")
            print(f"Backend: {health_data.get('status')}  |  Tools: {health_data.get('tools_loaded')}  |  LLMs: {health_data.get('llm_providers')}")
        except Exception as e:
            print(f"\nBackend not reachable at {base_url}: {e}")
            print("Start the backend first: python main.py")
            sys.exit(1)

        print(f"\nRunning {len(cases)} test case(s)...\n")

        results = []
        for i, case in enumerate(cases, 1):
            print(f"  [{i:2}/{len(cases)}] Running: {case['id']}", end="\r")
            result = await _run_case(client, base_url, case)
            results.append(result)
            _print_result(result, i, len(cases))
            if i < len(cases):
                await asyncio.sleep(15)  # avoid hitting free-tier TPM limits

    # Summary
    passed = sum(1 for r in results if r.get("status") == "pass")
    failed = sum(1 for r in results if r.get("status") == "fail")
    errors = sum(1 for r in results if r.get("status") in ("timeout", "error", "api_error"))
    avg_score = round(sum(r.get("score_pct", 0) for r in results) / len(results), 1) if results else 0
    avg_time = round(sum(r.get("elapsed_s", 0) for r in results) / len(results), 1) if results else 0

    print(f"\n{'-' * 60}")
    print(f"  Results: {passed} passed  {failed} failed  {errors} errors  ({len(results)} total)")
    print(f"  Avg score: {avg_score}%   Avg latency: {avg_time}s")
    print(f"{'-' * 60}\n")

    report = {
        "run_at": datetime.utcnow().isoformat() + "Z",
        "backend_url": base_url,
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "avg_score_pct": avg_score,
        "avg_latency_s": avg_time,
        "results": results,
    }

    out_file = out_path or f"evals/results_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    Path(out_file).write_text(json.dumps(report, indent=2))
    print(f"  Full report written to: {out_file}\n")

    sys.exit(0 if failed == 0 and errors == 0 else 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run ClarityAI evals against a live backend")
    parser.add_argument("--url", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--case", default=None, help="Run a single case by ID")
    parser.add_argument("--out", default=None, help="Output JSON path (default: auto-timestamped)")
    args = parser.parse_args()

    asyncio.run(run(args.url, args.case, args.out))
