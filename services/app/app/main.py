from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.database import check_database, read_project_stage
from app.integrations.deepseek import DeepSeekGateway


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings()
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
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


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
        "next_milestone": "数据资源目录与业务知识管理",
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

