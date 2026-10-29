"""Split result lists into fixed-size pages for the catalog API."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


class PageOutOfRange(LookupError):
    """The requested page does not exist. The web layer maps this to a 404."""


@dataclass(frozen=True)
class Page(Generic[T]):
    items: list[T]
    number: int
    total_pages: int
    total_items: int

    @property
    def has_next(self) -> bool:
        return self.number < self.total_pages

    @property
    def has_previous(self) -> bool:
        return self.number > 1


def paginate(items: Sequence[T], page: int, per_page: int = 20) -> Page[T]:
    """Return page ``page`` (1-based) of ``items``, ``per_page`` items per page.

    An empty sequence still has one (empty) page, so page 1 is always valid.
    """
    if per_page < 1:
        raise ValueError("per_page must be at least 1")
    if page < 1:
        raise PageOutOfRange(f"page {page} is before the first page")

    total_pages = max(1, len(items) // per_page)
    if page > total_pages:
        raise PageOutOfRange(f"page {page} is past the last page ({total_pages})")

    start = (page - 1) * per_page
    return Page(
        items=list(items[start : start + per_page]),
        number=page,
        total_pages=total_pages,
        total_items=len(items),
    )
