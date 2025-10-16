"""Persistent storage helpers for the library management system.

The application stores its data in simple JSON files on disk.  This module
contains helper functions for loading and saving users, authors, books,
loans and authentication tokens.  If the relevant data files do not
exist, they are created with sensible default contents (an empty list
or dictionary).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from models import User, Author, Book, Loan


# Define the directory where all data files live
DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)


def _load_json(path: Path, default: object) -> object:
    """Load JSON from the given file.  If it doesn't exist, return default."""
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            # If the file is corrupt, return default
            return default


def _save_json(path: Path, data: object) -> None:
    """Write data as JSON to the given file atomically."""
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def load_users() -> List[User]:
    users_path = DATA_DIR / "users.json"
    raw = _load_json(users_path, default=[])
    return [User(**item) for item in raw]


def save_users(users: List[User]) -> None:
    users_path = DATA_DIR / "users.json"
    raw = [user.__dict__ for user in users]
    _save_json(users_path, raw)


def load_authors() -> List[Author]:
    authors_path = DATA_DIR / "authors.json"
    raw = _load_json(authors_path, default=[])
    return [Author(**item) for item in raw]


def save_authors(authors: List[Author]) -> None:
    authors_path = DATA_DIR / "authors.json"
    raw = [author.__dict__ for author in authors]
    _save_json(authors_path, raw)


def load_books() -> List[Book]:
    books_path = DATA_DIR / "books.json"
    raw = _load_json(books_path, default=[])
    return [Book(**item) for item in raw]


def save_books(books: List[Book]) -> None:
    books_path = DATA_DIR / "books.json"
    raw = [book.__dict__ for book in books]
    _save_json(books_path, raw)


def load_loans() -> List[Loan]:
    loans_path = DATA_DIR / "loans.json"
    raw = _load_json(loans_path, default=[])
    return [Loan(**item) for item in raw]


def save_loans(loans: List[Loan]) -> None:
    loans_path = DATA_DIR / "loans.json"
    raw = [loan.__dict__ for loan in loans]
    _save_json(loans_path, raw)


def load_tokens() -> Dict[str, int]:
    """Return a mapping of token strings to user_id."""
    tokens_path = DATA_DIR / "tokens.json"
    raw = _load_json(tokens_path, default={})
    # Ensure values are integers
    return {token: int(user_id) for token, user_id in raw.items()}


def save_tokens(tokens: Dict[str, int]) -> None:
    tokens_path = DATA_DIR / "tokens.json"
    _save_json(tokens_path, tokens)
