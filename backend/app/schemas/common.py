"""
NAADAMAYA shared schema pieces.

- APIModel: the base class for every response/request schema.
- MessageResponse: a plain "it worked" reply.
- ErrorResponse: the shape of every error (used for OpenAPI documentation;
  the real errors are built by middleware/error_handler.py).
- Page / PageParams: pagination, so no endpoint returns thousands of rows.

All field names are snake_case. The frontend report adapter converts them to
the shapes its components already use, so no component changes.
"""

from typing import Any, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

MAX_PAGE_SIZE = 50
DEFAULT_PAGE_SIZE = 20


class APIModel(BaseModel):
    """Base for all schemas. Reads straight from SQLAlchemy objects."""

    model_config = ConfigDict(
        from_attributes=True,
        str_strip_whitespace=True,
        populate_by_name=True,
    )


class MessageResponse(APIModel):
    success: bool = True
    message: str


# ==========================================================
# Errors (documentation shape)
# ==========================================================
class ErrorBody(APIModel):
    code: str = Field(examples=["USAGE_LIMIT_REACHED"])
    message: str = Field(examples=["Monthly analysis limit reached."])
    # Extra public fields may appear here, e.g. upgrade_required or retry_after.
    model_config = ConfigDict(extra="allow")


class ErrorResponse(APIModel):
    success: bool = False
    error: ErrorBody
    request_id: str | None = None


# Reused in route decorators so Swagger shows the possible errors.
COMMON_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Authentication required or session expired."},
    403: {"model": ErrorResponse, "description": "Not allowed."},
    404: {"model": ErrorResponse, "description": "Not found."},
    422: {"model": ErrorResponse, "description": "Invalid input."},
    429: {"model": ErrorResponse, "description": "Too many requests."},
}


# ==========================================================
# Pagination
# ==========================================================
class PageParams:
    """FastAPI dependency: `params: PageParams = Depends()`."""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number, starting at 1."),
        page_size: int = Query(
            DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Items per page (max 50)."
        ),
    ) -> None:
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class Page(APIModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
    has_more: bool

    @classmethod
    def build(cls, items: list[T], total: int, params: PageParams) -> "Page[T]":
        return cls(
            items=items,
            page=params.page,
            page_size=params.page_size,
            total=total,
            has_more=params.offset + len(items) < total,
        )
