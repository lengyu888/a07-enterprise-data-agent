from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.data_import.service import ImportValidationError, import_csv, list_templates, recent_imports


router = APIRouter(prefix="/api/v1/data-imports", tags=["data-import"])


class CsvImportRequest(BaseModel):
    template_code: str = Field(min_length=3, max_length=50)
    filename: str = Field(default="import.csv", min_length=1, max_length=255)
    csv_text: str = Field(min_length=1, max_length=1_000_000)


@router.get("/templates")
def templates() -> list[dict[str, object]]:
    return list_templates()


@router.get("")
def imports(limit: int = Query(default=10, ge=1, le=30)) -> list[dict[str, object]]:
    return recent_imports(limit)


@router.post("")
def create_import(payload: CsvImportRequest) -> dict[str, object]:
    try:
        return import_csv(payload.template_code, payload.filename, payload.csv_text)
    except ImportValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "errors": exc.errors},
        ) from exc
