"""Universal pagination, search, filtering and sorting for SQLAlchemy queries.

``PaginationParams`` captures the common list-query knobs; ``paginate`` applies
them to a query and returns a JSON-serialisable envelope:

    {items, total, page, limit, pages, next_page, prev_page}

Search/filter/sort are applied only against real columns of the provided model,
so untrusted ``sort_by`` / ``filters`` keys can't reach arbitrary SQL.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

from sqlalchemy import or_
from sqlalchemy.orm import Query

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


@dataclass
class PaginationParams:
    page: int = 1
    limit: int = DEFAULT_LIMIT
    search: str | None = None
    sort_by: str = "created_at"
    sort_order: str = "desc"  # "asc" | "desc"
    filters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Clamp to sane bounds (defensive against client input).
        self.page = max(1, int(self.page or 1))
        self.limit = min(MAX_LIMIT, max(1, int(self.limit or DEFAULT_LIMIT)))
        self.sort_order = "asc" if str(self.sort_order).lower() == "asc" else "desc"
        if self.search is not None:
            self.search = self.search.strip() or None
        self.filters = {k: v for k, v in (self.filters or {}).items() if v is not None}


def _apply_filters(query: Query, model, filters: dict[str, Any]) -> Query:
    for key, value in filters.items():
        column = getattr(model, key, None)
        if column is not None:
            query = query.filter(column == value)
    return query


def _apply_search(query: Query, model, search: str, search_fields: Sequence[str]) -> Query:
    like = f"%{search}%"
    conditions = [getattr(model, f).ilike(like) for f in search_fields if hasattr(model, f)]
    if conditions:
        query = query.filter(or_(*conditions))
    return query


def _apply_sort(query: Query, model, sort_by: str, sort_order: str, allowed_sort: Iterable[str] | None) -> Query:
    if allowed_sort is not None and sort_by not in set(allowed_sort):
        sort_by = "created_at"
    column = getattr(model, sort_by, None) or getattr(model, "created_at", None) or getattr(model, "id", None)
    if column is None:
        return query
    return query.order_by(column.asc() if sort_order == "asc" else column.desc())


def paginate(
    query: Query,
    params: PaginationParams,
    *,
    model=None,
    search_fields: Sequence[str] | None = None,
    allowed_sort: Iterable[str] | None = None,
    serializer: Callable[[Any], Any] | None = None,
) -> dict[str, Any]:
    """Apply search/filter/sort + pagination and return a result envelope."""
    if model is not None:
        if params.filters:
            query = _apply_filters(query, model, params.filters)
        if params.search and search_fields:
            query = _apply_search(query, model, params.search, search_fields)
        query = _apply_sort(query, model, params.sort_by, params.sort_order, allowed_sort)

    total = query.count()
    pages = max(1, math.ceil(total / params.limit)) if total else 1
    page = min(params.page, pages) if total else 1

    rows = query.offset((page - 1) * params.limit).limit(params.limit).all()
    items = [serializer(r) for r in rows] if serializer else rows

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": params.limit,
        "pages": pages,
        "next_page": page + 1 if page < pages else None,
        "prev_page": page - 1 if page > 1 else None,
    }
