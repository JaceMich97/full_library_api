"""Authentication and authorization helpers.

This module implements user registration, login and token management
without any external dependencies.  Passwords are hashed using SHA‑256
and authentication tokens are generated using the ``secrets`` module.

Tokens are stored in a JSON file (via ``storage.load_tokens`` and
``storage.save_tokens``).  When a user logs in, a new token is created
and associated with their user ID.  The token must be provided as
``Authorization: Token <token>`` in subsequent API requests.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Optional, Tuple

from models import User
import storage


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def register_user(username: str, email: str, password: str, role: str = "MEMBER") -> Tuple[Optional[User], Optional[str]]:
    """Register a new user.

    Returns (user, error) where error is None on success or an error string
    describing why registration failed.  Usernames and emails must be
    unique.  Passwords are hashed before storage.
    """
    users = storage.load_users()
    if any(u.username.lower() == username.lower() for u in users):
        return None, "username_taken"
    if any(u.email.lower() == email.lower() for u in users):
        return None, "email_taken"
    # Compute next ID
    next_id = max([u.id for u in users], default=0) + 1
    password_hash = _hash_password(password)
    new_user = User(id=next_id, username=username, email=email, password_hash=password_hash, role=role.upper())
    users.append(new_user)
    storage.save_users(users)
    return new_user, None


def authenticate_user(username: str, password: str) -> Optional[User]:
    """Return the user object if the username and password are correct, else None."""
    users = storage.load_users()
    password_hash = _hash_password(password)
    for u in users:
        if u.username.lower() == username.lower() and u.password_hash == password_hash:
            return u
    return None


def login(username: str, password: str) -> Tuple[Optional[str], Optional[str]]:
    """Attempt to log in a user.

    Returns (token, error).  On success token is a newly generated authentication
    token string associated with the user's ID; on failure error is a string
    such as "invalid_credentials".
    """
    user = authenticate_user(username, password)
    if not user:
        return None, "invalid_credentials"
    tokens = storage.load_tokens()
    # Generate a token that isn't already in use
    token: str
    while True:
        token = secrets.token_hex(16)
        if token not in tokens:
            break
    tokens[token] = user.id
    storage.save_tokens(tokens)
    return token, None


def logout(token: str) -> bool:
    """Invalidate a token.  Returns True if the token existed and was removed."""
    tokens = storage.load_tokens()
    if token in tokens:
        tokens.pop(token)
        storage.save_tokens(tokens)
        return True
    return False


def get_user_by_token(token: str) -> Optional[User]:
    """Return the User associated with a given token, or None if not found."""
    tokens = storage.load_tokens()
    user_id = tokens.get(token)
    if user_id is None:
        return None
    users = storage.load_users()
    return next((u for u in users if u.id == user_id), None)


def require_role(user: Optional[User], roles: list[str]) -> bool:
    """Return True if the user is authenticated and has a role in roles."""
    return user is not None and user.role.upper() in [r.upper() for r in roles]
