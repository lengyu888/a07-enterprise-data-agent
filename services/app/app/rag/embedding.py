from __future__ import annotations

from functools import lru_cache

from fastembed import TextEmbedding

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_embedding_model() -> TextEmbedding:
    settings = get_settings()
    return TextEmbedding(
        model_name=settings.embedding_model,
        cache_dir=settings.embedding_cache_path,
        local_files_only=True,
        threads=2,
    )


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return [vector.astype(float).tolist() for vector in get_embedding_model().embed(texts)]


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"
