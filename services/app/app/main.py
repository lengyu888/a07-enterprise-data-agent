from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.api.agent import router as agent_router
from app.api.catalog import router as catalog_router
from app.api.knowledge import router as knowledge_router
from app.api.rag import router as rag_router
from app.catalog.service import refresh_catalog
from app.core.config import get_settings
from app.core.database import check_database, read_project_stage
from app.core.migrations import run_migrations
from app.integrations.deepseek import DeepSeekGateway
from app.rag.indexer import ensure_index


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings()
    run_migrations()
    refresh_catalog()
    ensure_index()
    yield


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="A07 competition edition modular monolith API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)

app.include_router(catalog_router)
app.include_router(knowledge_router)
app.include_router(agent_router)
app.include_router(rag_router)


@app.get("/api/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="a07-app",
        version=settings.app_version,
    )


@app.get("/api/ready", tags=["system"])
def ready() -> dict[str, object]:
    try:
        database_ready = check_database()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc

    return {
        "status": "ready" if database_ready else "not_ready",
        "dependencies": {
            "database": "ready" if database_ready else "not_ready",
            "deepseek": "configured" if settings.deepseek_configured else "not_configured",
        },
    }


@app.get("/api/v1/system/bootstrap", tags=["system"])
def bootstrap() -> dict[str, object]:
    return {
        "project": "A07 企业数据底座智能问析 Agent",
        "edition": "contest",
        "phase": read_project_stage(),
        "architecture": ["Vue 3", "FastAPI", "PostgreSQL + pgvector"],
        "core_innovation": ["DeepSeek", "LangGraph", "RAG", "Text-to-SQL"],
        "next_milestone": "设备异常识别与异常下钻",
    }


@app.post("/api/v1/system/deepseek/probe", tags=["system"])
def probe_deepseek() -> dict[str, str]:
    if not settings.deepseek_configured:
        raise HTTPException(
            status_code=412,
            detail="DEEPSEEK_API_KEY is not configured in the server environment",
        )

    try:
        result = DeepSeekGateway(settings).probe()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"DeepSeek probe failed: {type(exc).__name__}") from exc

    return {
        "status": "ready",
        "model": result.model,
        "content": result.content,
    }
