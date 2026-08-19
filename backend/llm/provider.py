"""
LLM provider — Mistral only.

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

_MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")


def _build_providers(temperature: float) -> List[BaseChatModel]:
    """Build the Mistral LLM provider."""
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "MISTRAL_API_KEY is required. Add it to your .env file."
        )

    try:
        from langchain_mistralai import ChatMistralAI
    except ImportError as exc:
        raise EnvironmentError(
            "langchain-mistralai is not installed. Run: pip install langchain-mistralai"
        ) from exc

    provider = ChatMistralAI(
        model=_MISTRAL_MODEL,
        api_key=api_key,
        temperature=temperature,
        max_retries=0,
    )
    logger.info("LLM provider: Mistral (%s)", _MISTRAL_MODEL)
    return [provider]


def create_llm(temperature: float = 0) -> BaseChatModel:
    """Return a plain chat LLM."""
    return _build_providers(temperature)[0]


def create_structured_llm(schema: Type[BaseModel], temperature: float = 0):
    """Return a structured-output LLM."""
    return _build_providers(temperature)[0].with_structured_output(schema)


def create_tool_llm(tools: list, temperature: float = 0.1):
    """Return a tool-calling LLM."""
    return _build_providers(temperature)[0].bind_tools(tools)


def get_provider_names() -> List[str]:
    """Return display names for active providers (for health checks)."""
    if os.environ.get("MISTRAL_API_KEY"):
        return ["Mistral"]
    return []
