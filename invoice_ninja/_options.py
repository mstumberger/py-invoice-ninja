"""Shared helpers for list options objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

__all__ = ["CommonListOptions"]


@dataclass
class CommonListOptions:
    """Fields shared by most list options, serialized to query parameters."""

    def _common_query_items(self) -> List[tuple[str, str]]:
        items: List[tuple[str, str]] = []
        per_page = getattr(self, "per_page", 0)
        if per_page > 0:
            items.append(("per_page", str(per_page)))
        page = getattr(self, "page", 0)
        if page > 0:
            items.append(("page", str(page)))
        for attr in ("filter", "client_id", "status", "created_at", "updated_at", "sort", "include", "balance", "number", "vendor_id"):
            value = getattr(self, attr, "")
            if value:
                items.append((attr, value))
        is_deleted = getattr(self, "is_deleted", None)
        if is_deleted is not None:
            items.append(("is_deleted", "true" if is_deleted else "false"))
        return items

    def to_query(self) -> Dict[str, List[str]]:
        """Convert the options to query parameters (multi-valued, like Go's
        ``url.Values``)."""
        query: Dict[str, List[str]] = {}
        for key, value in self._common_query_items():
            query.setdefault(key, []).append(value)
        return query
