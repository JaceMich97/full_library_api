"""Data models for the library management system.

We define simple dataclasses to model Users, Authors, Books and Loans.  These
dataclasses are used by the application server to store and manipulate
objects loaded from JSON storage.  Where appropriate we include helper
methods for updating status or computing derived values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class User:
    """Representation of an API user.

    Attributes:
        id: unique integer identifier.
        username: unique username.
        email: email address.
        password_hash: SHA‑256 hash of the user's password.
        role: one of "MEMBER", "LIBRARIAN" or "ADMIN".
    """

    id: int
    username: str
    email: str
    password_hash: str
    role: str  # MEMBER, LIBRARIAN or ADMIN


@dataclass
class Author:
    """Represents an author of one or more books."""
    id: int
    name: str


@dataclass
class Book:
    """Represents a book in the library."""
    id: int
    title: str
    publication_year: int
    isbn: str
    author_id: int
    total_copies: int
    available_copies: int


@dataclass
class Loan:
    """Represents a borrowing transaction between a user and a book."""
    id: int
    user_id: int
    book_id: int
    borrowed_at: str  # ISO format datetime
    due_at: str       # ISO format datetime
    returned_at: Optional[str] = None  # ISO format datetime or None

    def is_overdue(self) -> bool:
        """Return True if the loan is overdue (due date in the past and not yet returned)."""
        if self.returned_at is not None:
            return False
        return datetime.fromisoformat(self.due_at) < datetime.utcnow()

    @property
    def status(self) -> str:
        """Human readable status: BORROWED or RETURNED."""
        return "RETURNED" if self.returned_at is not None else "BORROWED"
