import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from api import app_state
from api.routes import router
from api.document_routes import document_router
from documents.store import init_db
from graph.workflow import create_workflow
from langchain_mcp_adapters.tools import load_mcp_tools
from tools.tavily_mcp import build_mcp_client
from tools.financial import get_financial_data

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
    _validate_env()

    # Initialise document store (creates SQLite tables if missing)
    await init_db()
    logger.info("Document store ready.")

    # Resolve checkpointer — prefer SQLite for persistence, fall back to MemorySaver
    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        _sqlite_available = True
    except ImportError:
        _sqlite_available = False
        logger.warning(
            "langgraph-checkpoint-sqlite not installed — "
            "conversation state will not persist across restarts. "
            "Run: pip install langgraph-checkpoint-sqlite"
        )

    mcp_client = build_mcp_client()
    logger.info("Starting Tavily MCP server...")

    async with mcp_client.session("tavily") as session:
        mcp_tools = await load_mcp_tools(session)
        all_tools = mcp_tools + [get_financial_data]

        logger.info(
            "Tools loaded: %s", [t.name for t in all_tools]
        )

        if _sqlite_available:
            async with AsyncSqliteSaver.from_conn_string("clarity_checkpoints.db") as checkpointer:
                logger.info("Persistent SQLite checkpointer active (clarity_checkpoints.db).")
                app_state["graph"] = create_workflow(all_tools, checkpointer)
                app_state["tools"] = all_tools
                logger.info("LangGraph workflow compiled and ready.")
                yield
        else:
            from langgraph.checkpoint.memory import MemorySaver
            app_state["graph"] = create_workflow(all_tools, MemorySaver())
            app_state["tools"] = all_tools
            logger.info("LangGraph workflow compiled (in-memory state).")
            yield

    app_state.clear()
    logger.info("MCP client closed. Application shutdown complete.")


app = FastAPI(
    title="ClarityAI",
    description="Multi-agent business research assistant",
    version="2.0.0",
    lifespan=lifespan,
)

_raw_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(document_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000)
