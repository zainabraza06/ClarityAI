import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from api import app_state
from api.routes import router
from graph.workflow import create_workflow
from langchain_mcp_adapters.tools import load_mcp_tools
from tools.tavily_mcp import build_mcp_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(name)s — %(message)s",
)
logger = logging.getLogger("clarityai")


def _validate_env() -> None:
    llm_keys = ("OPENROUTER_API_KEY", "GROQ_API_KEY", "GOOGLE_API_KEY")
    if not any(os.environ.get(k) for k in llm_keys):
        raise EnvironmentError(
            f"No LLM API key found. Set at least one of: {', '.join(llm_keys)}"
        )
    if not os.environ.get("TAVILY_API_KEY"):
        raise EnvironmentError(
            "TAVILY_API_KEY is required. Add it to your .env file."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan handler.

    Starts the Tavily MCP server as a subprocess (via npx), loads the LangChain
    tool wrappers, compiles the LangGraph workflow, then keeps everything alive
    until the app shuts down.
    """
    _validate_env()
    logger.info("Starting Tavily MCP server...")

    mcp_client = build_mcp_client()

    # v0.2.x API: use client.session() context manager to keep the MCP server alive
    async with mcp_client.session("tavily") as session:
        tools = await load_mcp_tools(session)
        logger.info(
            "Tavily MCP ready — tools available: %s",
            [t.name for t in tools],
        )

        app_state["graph"] = create_workflow(tools)
        app_state["tools"] = tools
        logger.info("LangGraph workflow compiled and ready.")

        yield

    app_state.clear()
    logger.info("MCP client closed. Application shutdown complete.")


app = FastAPI(
    title="ClarityAI",
    description="Multi-agent business research assistant",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000)
