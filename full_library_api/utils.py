"""Utility functions for query parameter parsing and data manipulation."""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Tuple

from models import Author, Book, Loan


def parse_query_params(query_string: str) -> Dict[str, str]:
    """Parse the query string into a simple key->value dict (only first value considered)."""
    from urllib.parse import parse_qs
    params = parse_qs(query_string, keep_blank_values=True)
    return {k: v[0] for k, v in params.items() if v}


def paginate(items: List[Any], page: int, page_size: int) -> Tuple[List[Any], Dict[str, int]]:
    """Return a slice of items for the given page and page_size, along with pagination info."""
    total = len(items)
    page = max(page, 1)
    page_size = max(page_size, 1)
    start = (page - 1) * page_size
    end = start + page_size
    paged = items[start:end]
    return paged, {
        "count": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if page_size > 0 else 1,
    }


def apply_author_search(authors: List[Author], search: str) -> List[Author]:
    if not search:
        return authors
    term = search.lower()
    return [a for a in authors if term in a.name.lower()]


def apply_author_order(authors: List[Author], ordering: str) -> List[Author]:
    if not ordering:
        return authors
    reverse = False
    field = ordering
    if ordering.startswith("-"):
        reverse = True
        field = ordering[1:]
    key_funcs = {
        "id": lambda a: a.id,
        "name": lambda a: a.name.lower(),
    }
    if field not in key_funcs:
        return authors
    return sorted(authors, key=key_funcs[field], reverse=reverse)


def apply_book_search(books: List[Book], authors: List[Author], search: str) -> List[Book]:
    if not search:
        return books
    term = search.lower()
    # Prebuild author lookup
    author_lookup = {a.id: a for a in authors}
    filtered: List[Book] = []
    for b in books:
        if term in b.title.lower():
            filtered.append(b)
        else:
            author = author_lookup.get(b.author_id)
            if author and term in author.name.lower():
                filtered.append(b)
    return filtered


def apply_book_filters(books: List[Book], params: Dict[str, str]) -> List[Book]:
    filtered = books
    # Filter by author id
    if "author" in params:
        try:
            author_id = int(params["author"])
            filtered = [b for b in filtered if b.author_id == author_id]
        except ValueError:
            pass
    # Filter by publication year
    if "publication_year" in params:
        try:
            year = int(params["publication_year"])
            filtered = [b for b in filtered if b.publication_year == year]
        except ValueError:
            pass
    return filtered


def apply_book_order(books: List[Book], ordering: str) -> List[Book]:
    if not ordering:
        return books
    reverse = False
    field = ordering
    if ordering.startswith("-"):
        reverse = True
        field = ordering[1:]
    key_funcs = {
        "id": lambda b: b.id,
        "title": lambda b: b.title.lower(),
        "publication_year": lambda b: b.publication_year,
        "author": lambda b: b.author_id,
    }
    if field not in key_funcs:
        return books
    return sorted(books, key=key_funcs[field], reverse=reverse)


def apply_loan_filters(loans: List[Loan], params: Dict[str, str]) -> List[Loan]:
    filtered = loans
    # filter by user_id
    if "user_id" in params:
        try:
            uid = int(params["user_id"])
            filtered = [l for l in filtered if l.user_id == uid]
        except ValueError:
            pass
    # filter by status
    if "status" in params:
        status = params["status"].upper()
        if status in {"BORROWED", "RETURNED"}:
            if status == "BORROWED":
                filtered = [l for l in filtered if l.returned_at is None]
            else:
                filtered = [l for l in filtered if l.returned_at is not None]
    # filter overdue
    if params.get("overdue", "false").lower() == "true":
        filtered = [l for l in filtered if l.is_overdue()]
    return filtered


def apply_loan_order(loans: List[Loan], ordering: str) -> List[Loan]:
    if not ordering:
        return loans
    reverse = False
    field = ordering
    if ordering.startswith("-"):
        reverse = True
        field = ordering[1:]
    key_funcs = {
        "id": lambda l: l.id,
        "borrowed_at": lambda l: l.borrowed_at,
        "due_at": lambda l: l.due_at,
    }
    if field not in key_funcs:
        return loans
    return sorted(loans, key=key_funcs[field], reverse=reverse)
