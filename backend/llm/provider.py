"""
LLM provider with four-tier fallback: OpenRouter → Groq → Gemini → Mistral.

Only providers whose API key is present in the environment are included.
The first available key in priority order becomes the primary; the rest form
the fallback chain via LangChain's built-in `with_fallbacks()`.

Priority order:  OPENROUTER_API_KEY  →  GROQ_API_KEY  →  GOOGLE_API_KEY  →  MISTRAL_API_KEY

Usage:
    from llm.provider import create_llm, create_structured_llm, create_tool_llm

    llm            = create_llm()                           # plain chat
    structured_llm = create_structured_llm(MyPydanticModel) # structured output
    tool_llm       = create_tool_llm(tools)                 # tool calling
"""

import logging
import os
from typing import List, Type

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

logger = logging.getLogger("clarityai.llm")

# Model defaults — override via env vars if desired
_OPENROUTER_MODEL = os.environ.get(
    "OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"
)
_GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
_MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")


def _build_providers(temperature: float) -> List[BaseChatModel]:
    """
    Build an ordered list of available LLM providers.
    Providers are included only when their API key is set.
    Set LLM_PROVIDERS=groq to use Groq only (useful when other providers are rate-limited).
    Set LLM_PROVIDERS=mistral to use Mistral only.
    """
    providers: List[BaseChatModel] = []
    _only = os.environ.get("LLM_PROVIDERS", "").lower()  # e.g. "groq" or "" for all

    # ── 1. OpenRouter (OpenAI-compatible endpoint) ──────────────────────────
    if os.environ.get("OPENROUTER_API_KEY") and (_only in ("", "openrouter")):
        try:
            from langchain_openai import ChatOpenAI

            providers.append(
                ChatOpenAI(
                    model=_OPENROUTER_MODEL,
                    base_url="https://openrouter.ai/api/v1",
                    api_key=os.environ["OPENROUTER_API_KEY"],
                    temperature=temperature,
                    max_retries=0,  # don't retry; let fallback chain handle 429s
                    default_headers={
                        "HTTP-Referer": "https://clarityai.app",
                        "X-Title": "ClarityAI",
                    },
                )
            )
            logger.info("LLM provider: OpenRouter (%s)", _OPENROUTER_MODEL)
        except ImportError:
            logger.warning("langchain-openai not installed — skipping OpenRouter")

    # ── 2. Groq ──────────────────────────────────────────────────────────────
    if os.environ.get("GROQ_API_KEY") and (_only in ("", "groq")):
        try:
            from langchain_groq import ChatGroq

            providers.append(
                ChatGroq(
                    model=_GROQ_MODEL,
                    api_key=os.environ["GROQ_API_KEY"],
                    temperature=temperature,
                    max_retries=0,  # fail fast; let fallback chain handle 429s
                )
            )
            logger.info("LLM provider: Groq (%s)", _GROQ_MODEL)
        except ImportError:
            logger.warning("langchain-groq not installed — skipping Groq")

    # ── 3. Google Gemini ─────────────────────────────────────────────────────
    if os.environ.get("GOOGLE_API_KEY") and (_only in ("", "gemini", "google")):
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI

            providers.append(
                ChatGoogleGenerativeAI(
                    model=_GEMINI_MODEL,
                    google_api_key=os.environ["GOOGLE_API_KEY"],
                    temperature=temperature,
                    max_retries=0,  # fail fast; don't block for minutes on quota errors
                )
            )
            logger.info("LLM provider: Gemini (%s)", _GEMINI_MODEL)
        except ImportError:
            logger.warning(
                "langchain-google-genai not installed — skipping Gemini"
            )

    # ── 4. Mistral (no daily cap on free tier, 1 req/sec) ───────────────────
    if os.environ.get("MISTRAL_API_KEY") and (_only in ("", "mistral")):
        try:
            from langchain_mistralai import ChatMistralAI

            providers.append(
                ChatMistralAI(
                    model=_MISTRAL_MODEL,
                    api_key=os.environ["MISTRAL_API_KEY"],
                    temperature=temperature,
                    max_retries=0,
                )
            )
            logger.info("LLM provider: Mistral (%s)", _MISTRAL_MODEL)
        except ImportError:
            logger.warning("langchain-mistralai not installed — skipping Mistral")

    if not providers:
        raise EnvironmentError(
            "No LLM API key found. Set at least one of: "
            "OPENROUTER_API_KEY, GROQ_API_KEY, GOOGLE_API_KEY, MISTRAL_API_KEY"
        )

    if len(providers) > 1:
        logger.info(
            "Fallback chain active: %s",
            " → ".join(type(p).__name__ for p in providers),
        )

    return providers


def create_llm(temperature: float = 0) -> BaseChatModel:
    """Return a plain chat LLM with automatic provider fallback."""
    providers = _build_providers(temperature)
    primary = providers[0]
    return primary.with_fallbacks(providers[1:]) if len(providers) > 1 else primary


def create_structured_llm(schema: Type[BaseModel], temperature: float = 0):
    """
    Return a structured-output LLM with automatic provider fallback.
    Each provider in the chain independently wraps the schema so parsing
    failures on one provider also trigger a fallback.
    """
    providers = _build_providers(temperature)
    structured = [p.with_structured_output(schema) for p in providers]
    primary = structured[0]
    return primary.with_fallbacks(structured[1:]) if len(structured) > 1 else primary


def create_tool_llm(tools: list, temperature: float = 0.1):
    """Return a tool-calling LLM with automatic provider fallback."""
    providers = _build_providers(temperature)
    tool_llms = [p.bind_tools(tools) for p in providers]
    primary = tool_llms[0]
    return primary.with_fallbacks(tool_llms[1:]) if len(tool_llms) > 1 else primary


def get_provider_names() -> List[str]:
    """Return display names for all active providers (for health checks)."""
    _only = os.environ.get("LLM_PROVIDERS", "").lower()
    names = []
    if os.environ.get("OPENROUTER_API_KEY") and (_only in ("", "openrouter")):
        names.append("OpenRouter")
    if os.environ.get("GROQ_API_KEY") and (_only in ("", "groq")):
        names.append("Groq")
    if os.environ.get("GOOGLE_API_KEY") and (_only in ("", "gemini", "google")):
        names.append("Gemini")
    if os.environ.get("MISTRAL_API_KEY") and (_only in ("", "mistral")):
        names.append("Mistral")
    return names
