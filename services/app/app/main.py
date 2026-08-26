from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, SecretStr

from app.api.agent import router as agent_router
from app.api.catalog import router as catalog_router
from app.api.knowledge import router as knowledge_router
from app.api.rag import router as rag_router
from app.catalog.service import refresh_catalog
from app.core.config import (
    get_runtime_deepseek_api_key,
    get_settings,
    replace_runtime_deepseek_config,
)
from app.core.database import check_database, read_project_stage
from app.core.migrations import run_migrations
from app.integrations.deepseek import DeepSeekGateway
from app.rag.indexer import ensure_index


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class DeepSeekConfigRequest(BaseModel):
    api_key: SecretStr | None = None
    model: Literal["deepseek-v4-pro", "deepseek-v4-flash"] = "deepseek-v4-pro"
    verify: bool = True


def deepseek_config_status(*, verified: bool | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "configured": settings.deepseek_configured,
        "status": "configured" if settings.deepseek_configured else "not_configured",
        "source": settings.deepseek_config_source,
        "model": settings.deepseek_model,
        "base_url": settings.deepseek_base_url,
        "reasoning_effort": settings.deepseek_reasoning_effort,
        "runtime_only": settings.deepseek_config_source == "runtime",
        "can_clear": bool(get_runtime_deepseek_api_key()),
    }
    if verified is not None:
        payload["verified"] = verified
    return payload


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
        "next_milestone": "真实演示闭环与答辩材料",
    }


@app.post("/api/v1/system/deepseek/probe", tags=["system"])
def probe_deepseek() -> dict[str, str]:
    if not settings.deepseek_configured:
        raise HTTPException(
            status_code=412,
            detail="请先在前端模型配置页面填写 DeepSeek API Key",
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


@app.get("/api/v1/system/deepseek/config", tags=["system"])
def get_deepseek_config() -> dict[str, object]:
    """Return only non-secret configuration metadata."""
    return deepseek_config_status()


@app.put("/api/v1/system/deepseek/config", tags=["system"])
def configure_deepseek(payload: DeepSeekConfigRequest) -> dict[str, object]:
    """Set a process-local key. The value is never persisted or returned."""
    api_key = payload.api_key.get_secret_value().strip() if payload.api_key else get_runtime_deepseek_api_key()
    if not api_key:
        raise HTTPException(status_code=422, detail="请先填写 DeepSeek API Key")
    if len(api_key) < 12 or len(api_key) > 256:
        raise HTTPException(status_code=422, detail="API Key 长度应为 12–256 个字符")

    previous = replace_runtime_deepseek_config(api_key, payload.model)
    if payload.verify:
        try:
            DeepSeekGateway(settings).probe()
        except Exception as exc:
            replace_runtime_deepseek_config(*previous)
            raise HTTPException(
                status_code=502,
                detail=f"DeepSeek 连接验证失败：{type(exc).__name__}",
            ) from exc

    return deepseek_config_status(verified=payload.verify)


@app.delete("/api/v1/system/deepseek/config", tags=["system"])
def clear_deepseek_config() -> dict[str, object]:
    """Clear the process-local key."""
    replace_runtime_deepseek_config(None, "deepseek-v4-pro")
    return deepseek_config_status()
