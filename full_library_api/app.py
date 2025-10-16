"""HTTP API server implementing a library management system.

This module exposes a simple HTTP API with endpoints for authentication,
authors, books and loans.  It uses only Python's standard library so
that it can run in restricted environments without external packages.

All requests and responses use JSON.  Clients should include
``Content-Type: application/json`` when sending a request body.  For
authenticated endpoints a header of the form ``Authorization: Token
<token>`` must be provided.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import auth
from models import Author, Book, Loan, User
import storage
import utils


class APIServer(BaseHTTPRequestHandler):
    """HTTP request handler for the Library API."""

    protocol_version = "HTTP/1.1"

    def _send_json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _parse_json_body(self) -> Optional[Dict[str, Any]]:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return None
        body_bytes = self.rfile.read(length)
        try:
            return json.loads(body_bytes)
        except json.JSONDecodeError:
            return None

    def _get_auth_user(self) -> Optional[User]:
        """Return the authenticated user based on the Authorization header, or None."""
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Token "):
            token = auth_header[6:].strip()
            return auth.get_user_by_token(token)
        return None

    # Helper to parse path, returning (base_path, id_or_none)
    def _parse_resource_path(self, path: str, prefix: str) -> Tuple[str, Optional[int]]:
        """Return (base_path, id) where id may be None if not present."""
        # ensure prefix ends with /
        if not prefix.endswith("/"):
            prefix = prefix + "/"
        if not path.startswith(prefix):
            return path, None
        remainder = path[len(prefix):]
        # if remainder is empty or '/', treat as list path
        if remainder == "" or remainder == "/":
            return prefix, None
        # expect a number followed by '/'
        parts = remainder.split('/')
        try:
            res_id = int(parts[0])
            # ensure no extra path beyond id/
            return prefix + f"{res_id}/", res_id
        except ValueError:
            return path, None

    def do_OPTIONS(self) -> None:
        # Allow CORS preflight if needed
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        # Authentication endpoints
        if path == "/api/auth/register/":
            body = self._parse_json_body() or {}
            username = body.get("username")
            email = body.get("email")
            password = body.get("password")
            role = body.get("role", "MEMBER")
            if not username or not email or not password:
                self._send_json({"detail": "Missing fields", "code": "invalid"}, status=HTTPStatus.BAD_REQUEST)
                return
            user, error = auth.register_user(username, email, password, role)
            if error == "username_taken":
                self._send_json({"detail": "Username already exists", "code": "username_taken"}, status=HTTPStatus.BAD_REQUEST)
                return
            if error == "email_taken":
                self._send_json({"detail": "Email already exists", "code": "email_taken"}, status=HTTPStatus.BAD_REQUEST)
                return
            # Success
            user_summary = {"id": user.id, "username": user.username, "email": user.email, "role": user.role}
            self._send_json(user_summary, status=HTTPStatus.CREATED)
            return
        if path == "/api/auth/login/":
            body = self._parse_json_body() or {}
            username = body.get("username")
            password = body.get("password")
            if not username or not password:
                self._send_json({"detail": "Missing credentials", "code": "invalid"}, status=HTTPStatus.BAD_REQUEST)
                return
            token, error = auth.login(username, password)
            if error:
                # Invalid credentials
                self._send_json({"detail": "Invalid username or password", "code": "invalid_credentials"}, status=HTTPStatus.UNAUTHORIZED)
                return
            self._send_json({"token": token})
            return
        if path == "/api/auth/logout/":
            user = self._get_auth_user()
            if not user:
                self._send_json({"detail": "Authentication required", "code": "not_authenticated"}, status=HTTPStatus.UNAUTHORIZED)
                return
            # Extract token from header
            token = self.headers.get("Authorization", "")[6:].strip() if self.headers.get("Authorization", "").startswith("Token ") else ""
            if auth.logout(token):
                # 204 No Content
                self.send_response(HTTPStatus.NO_CONTENT)
                self.end_headers()
            else:
                self._send_json({"detail": "Invalid token", "code": "invalid"}, status=HTTPStatus.UNAUTHORIZED)
            return

        # Loan borrow endpoint
        if path == "/api/loans/borrow/":
            user = self._get_auth_user()
            if not auth.require_role(user, ["MEMBER", "LIBRARIAN", "ADMIN"]):
                self._send_json({"detail": "Authentication required", "code": "not_authenticated"}, status=HTTPStatus.UNAUTHORIZED)
                return
            body = self._parse_json_body() or {}
            book_id = body.get("book_id") or body.get("book")
            if not book_id:
                self._send_json({"detail": "Missing book_id", "code": "invalid"}, status=HTTPStatus.BAD_REQUEST)
                return
            try:
                book_id = int(book_id)
            except ValueError:
                self._send_json({"detail": "Invalid book_id", "code": "invalid"}, status=HTTPStatus.BAD_REQUEST)
                return
            # Load data
            books = storage.load_books()
            book = next((b for b in books if b.id == book_id), None)
            if not book:
                self._send_json({"detail": "Book not found", "code": "not_found"}, status=HTTPStatus.NOT_FOUND)
                return
            if book.available_copies < 1:
                self._send_json({"detail": "No copies available", "code": "no_copies"}, status=HTTPStatus.CONFLICT)
                return
            # Load loans
            loans = storage.load_loans()
            # Prevent duplicate active loans for same user+book
            active_loan = next((l for l in loans if l.user_id == user.id and l.book_id == book_id and l.returned_at is None), None)
            if active_loan:
                self._send_json({"detail": "Book already borrowed by user", "code": "duplicate_loan"}, status=HTTPStatus.CONFLICT)
                return
            # Create loan
            next_id = max([l.id for l in loans], default=0) + 1
            now = datetime.utcnow()
            due = now + timedelta(days=14)
            new_loan = Loan(
                id=next_id,
                user_id=user.id,
                book_id=book_id,
                borrowed_at=now.isoformat(),
                due_at=due.isoformat(),
                returned_at=None,
            )
            loans.append(new_loan)
            # Update book copies
            book.available_copies -= 1
            storage.save_books(books)
            storage.save_loans(loans)
            self._send_json(new_loan.__dict__, status=HTTPStatus.CREATED)
            return
        # Loan return endpoint
        if path == "/api/loans/return/":
            user = self._get_auth_user()
            if not auth.require_role(user, ["MEMBER", "LIBRARIAN", "ADMIN"]):
                self._send_json({"detail": "Authentication required", "code": "not_authenticated"}, status=HTTPStatus.UNAUTHORIZED)
                return
            body = self._parse_json_body() or {}
            loan_id = body.get("loan_id")
            book_id = body.get("book_id") or body.get("book")
            # Load data
            loans = storage.load_loans()
            books = storage.load_books()
            target_loan: Optional[Loan] = None
            if loan_id is not None:
                try:
                    loan_id = int(loan_id)
                    target_loan = next((l for l in loans if l.id == loan_id), None)
                except ValueError:
                    pass
            elif book_id is not None:
                try:
                    book_id = int(book_id)
                    target_loan = next((l for l in loans if l.book_id == book_id and l.user_id == user.id and l.returned_at is None), None)
                except ValueError:
                    pass
            if not target_loan:
                self._send_json({"detail": "Loan not found", "code": "not_found"}, status=HTTPStatus.NOT_FOUND)
                return
            # Permissions: user must own the loan or be staff
            if target_loan.user_id != user.id and not auth.require_role(user, ["LIBRARIAN", "ADMIN"]):
                self._send_json({"detail": "Forbidden", "code": "permission_denied"}, status=HTTPStatus.FORBIDDEN)
                return
            if target_loan.returned_at is not None:
                self._send_json({"detail": "Loan already returned", "code": "already_returned"}, status=HTTPStatus.CONFLICT)
                return
            # Mark returned
            now = datetime.utcnow().isoformat()
            target_loan.returned_at = now
            # Increment available copies
            book = next((b for b in books if b.id == target_loan.book_id), None)
            if book:
                book.available_copies += 1
                storage.save_books(books)
            storage.save_loans(loans)
            self._send_json(target_loan.__dict__)
            return

        # Author create
        if path == "/api/authors/":
            # POST /api/authors/
            user = self._get_auth_user()
            if not auth.require_role(user, ["LIBRARIAN", "ADMIN"]):
                self._send_json({"detail": "Authentication required", "code": "not_authenticated"}, status=HTTPStatus.UNAUTHORIZED)
                return
            body = self._parse_json_body() or {}
            name = body.get("name")
            if not name:
                self._send_json({"detail": "Missing name", "code": "invalid"}, status=HTTPStatus.BAD_REQUEST)
                return
            authors = storage.load_authors()
            next_id = max([a.id for a in authors], default=0) + 1
            new_author = Author(id=next_id, name=name)
            authors.append(new_author)
            storage.save_authors(authors)
            self._send_json(new_author.__dict__, status=HTTPStatus.CREATED)
            return

        # Books create
        if path == "/api/books/":
            user = self._get_auth_user()
            if not auth.require_role(user, ["LIBRARIAN", "ADMIN"]):
                self._send_json({"detail": "Authentication required", "code": "not_authenticated"}, status=HTTPStatus.UNAUTHORIZED)
                return
            body = self._parse_json_body() or {}
            required_fields = ["title", "publication_year", "isbn", "author", "total_copies"]
            if not all(field in body for field in required_fields):
                self._send_json({"detail": "Missing fields", "code": "invalid"}, status=HTTPStatus.BAD_REQUEST)
                return
            # Validate and convert
            try:
                title = str(body["title"])
                publication_year = int(body["publication_year"])
                isbn = str(body["isbn"])
                author_id = int(body["author"])
                total_copies = int(body["total_copies"])
                available_copies = int(body.get("available_copies", total_copies))
            except (ValueError, TypeError):
                self._send_json({"detail": "Invalid field types", "code": "invalid"}, status=HTTPStatus.BAD_REQUEST)
                return
            # Ensure author exists
            authors = storage.load_authors()
            if not any(a.id == author_id for a in authors):
                self._send_json({"detail": "Author not found", "code": "invalid_author"}, status=HTTPStatus.BAD_REQUEST)
                return
            books = storage.load_books()
            next_id = max([b.id for b in books], default=0) + 1
            new_book = Book(
                id=next_id,
                title=title,
                publication_year=publication_year,
                isbn=isbn,
                author_id=author_id,
                total_copies=total_copies,
                available_copies=available_copies,
            )
            books.append(new_book)
            storage.save_books(books)
            self._send_json(new_book.__dict__, status=HTTPStatus.CREATED)
            return

        # Default not found
        self._send_json({"detail": "Not found", "code": "not_found"}, status=HTTPStatus.NOT_FOUND)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parsed.query

        # Authors list or detail
        base, res_id = self._parse_resource_path(path, "/api/authors/")
        if base.startswith("/api/authors/"):
            if res_id is None:
                # List authors
                params = utils.parse_query_params(query)
                page = int(params.get("page", 1) or 1)
                page_size = int(params.get("page_size", 10) or 10)
                search = params.get("search", "")
                ordering = params.get("ordering", "")
                authors = storage.load_authors()
                authors = utils.apply_author_search(authors, search)
                authors = utils.apply_author_order(authors, ordering)
                paged, pagination = utils.paginate(authors, page, page_size)
                # Represent authors as dicts
                data = [a.__dict__ for a in paged]
                # Optionally include pagination meta
                response = {
                    "results": data,
                    "count": pagination["count"],
                    "page": pagination["page"],
                    "page_size": pagination["page_size"],
                    "total_pages": pagination["total_pages"],
                }
                self._send_json(response)
                return
            else:
                authors = storage.load_authors()
                author = next((a for a in authors if a.id == res_id), None)
                if not author:
                    self._send_json({"detail": "Author not found", "code": "not_found"}, status=HTTPStatus.NOT_FOUND)
                    return
                self._send_json(author.__dict__)
                return

        # Books list or detail
        base, res_id = self._parse_resource_path(path, "/api/books/")
        if base.startswith("/api/books/"):
            if res_id is None:
                params = utils.parse_query_params(query)
                page = int(params.get("page", 1) or 1)
                page_size = int(params.get("page_size", 10) or 10)
                search = params.get("search", "")
                ordering = params.get("ordering", "")
                books = storage.load_books()
                authors = storage.load_authors()
                books = utils.apply_book_search(books, authors, search)
                books = utils.apply_book_filters(books, params)
                books = utils.apply_book_order(books, ordering)
                paged, pagination = utils.paginate(books, page, page_size)
                data = [b.__dict__ for b in paged]
                response = {
                    "results": data,
                    "count": pagination["count"],
                    "page": pagination["page"],
                    "page_size": pagination["page_size"],
                    "total_pages": pagination["total_pages"],
                }
                self._send_json(response)
                return
            else:
                books = storage.load_books()
                book = next((b for b in books if b.id == res_id), None)
                if not book:
                    self._send_json({"detail": "Book not found", "code": "not_found"}, status=HTTPStatus.NOT_FOUND)
                    return
                self._send_json(book.__dict__)
                return

        # Loans endpoints
        if path == "/api/loans/mine/":
            user = self._get_auth_user()
            if not user:
                self._send_json({"detail": "Authentication required", "code": "not_authenticated"}, status=HTTPStatus.UNAUTHORIZED)
                return
            params = utils.parse_query_params(query)
            page = int(params.get("page", 1) or 1)
            page_size = int(params.get("page_size", 10) or 10)
            status_filter = params.get("status")
            overdue = params.get("overdue")
            loans = storage.load_loans()
            # Filter to this user
            loans = [l for l in loans if l.user_id == user.id]
            # Apply status and overdue filters
            loans = utils.apply_loan_filters(loans, params)
            ordering = params.get("ordering", "")
            loans = utils.apply_loan_order(loans, ordering)
            paged, pagination = utils.paginate(loans, page, page_size)
            data = [loan.__dict__ | {"status": loan.status, "overdue": loan.is_overdue()} for loan in paged]
            response = {
                "results": data,
                "count": pagination["count"],
                "page": pagination["page"],
                "page_size": pagination["page_size"],
                "total_pages": pagination["total_pages"],
            }
            self._send_json(response)
            return

        # Staff list loans
        if path == "/api/loans/":
            user = self._get_auth_user()
            if not auth.require_role(user, ["LIBRARIAN", "ADMIN"]):
                self._send_json({"detail": "Forbidden", "code": "permission_denied"}, status=HTTPStatus.FORBIDDEN)
                return
            params = utils.parse_query_params(query)
            page = int(params.get("page", 1) or 1)
            page_size = int(params.get("page_size", 10) or 10)
            loans = storage.load_loans()
            loans = utils.apply_loan_filters(loans, params)
            loans = utils.apply_loan_order(loans, params.get("ordering", ""))
            paged, pagination = utils.paginate(loans, page, page_size)
            data = [loan.__dict__ | {"status": loan.status, "overdue": loan.is_overdue()} for loan in paged]
            response = {
                "results": data,
                "count": pagination["count"],
                "page": pagination["page"],
                "page_size": pagination["page_size"],
                "total_pages": pagination["total_pages"],
            }
            self._send_json(response)
            return

        # Get loan detail
        base, res_id = self._parse_resource_path(path, "/api/loans/")
        if base.startswith("/api/loans/") and res_id is not None:
            user = self._get_auth_user()
            if not user:
                self._send_json({"detail": "Authentication required", "code": "not_authenticated"}, status=HTTPStatus.UNAUTHORIZED)
                return
            loans = storage.load_loans()
            loan = next((l for l in loans if l.id == res_id), None)
            if not loan:
                self._send_json({"detail": "Loan not found", "code": "not_found"}, status=HTTPStatus.NOT_FOUND)
                return
            if loan.user_id != user.id and not auth.require_role(user, ["LIBRARIAN", "ADMIN"]):
                self._send_json({"detail": "Forbidden", "code": "permission_denied"}, status=HTTPStatus.FORBIDDEN)
                return
            data = loan.__dict__ | {"status": loan.status, "overdue": loan.is_overdue()}
            self._send_json(data)
            return

        # Default not found
        self._send_json({"detail": "Not found", "code": "not_found"}, status=HTTPStatus.NOT_FOUND)

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        # Update author
        base, res_id = self._parse_resource_path(path, "/api/authors/")
        if base.startswith("/api/authors/") and res_id is not None:
            user = self._get_auth_user()
            if not auth.require_role(user, ["LIBRARIAN", "ADMIN"]):
                self._send_json({"detail": "Forbidden", "code": "permission_denied"}, status=HTTPStatus.FORBIDDEN)
                return
            body = self._parse_json_body() or {}
            authors = storage.load_authors()
            author = next((a for a in authors if a.id == res_id), None)
            if not author:
                self._send_json({"detail": "Author not found", "code": "not_found"}, status=HTTPStatus.NOT_FOUND)
                return
            name = body.get("name")
            if name:
                author.name = name
                storage.save_authors(authors)
            self._send_json(author.__dict__)
            return

        # Update book
        base, res_id = self._parse_resource_path(path, "/api/books/")
        if base.startswith("/api/books/") and res_id is not None:
            user = self._get_auth_user()
            if not auth.require_role(user, ["LIBRARIAN", "ADMIN"]):
                self._send_json({"detail": "Forbidden", "code": "permission_denied"}, status=HTTPStatus.FORBIDDEN)
                return
            body = self._parse_json_body() or {}
            books = storage.load_books()
            book = next((b for b in books if b.id == res_id), None)
            if not book:
                self._send_json({"detail": "Book not found", "code": "not_found"}, status=HTTPStatus.NOT_FOUND)
                return
            # Update fields if provided
            if "title" in body:
                book.title = str(body["title"])
            if "publication_year" in body:
                try:
                    book.publication_year = int(body["publication_year"])
                except (TypeError, ValueError):
                    pass
            if "isbn" in body:
                book.isbn = str(body["isbn"])
            if "author" in body:
                try:
                    author_id = int(body["author"])
                    # Ensure author exists
                    authors = storage.load_authors()
                    if any(a.id == author_id for a in authors):
                        book.author_id = author_id
                except (TypeError, ValueError):
                    pass
            if "total_copies" in body:
                try:
                    new_total = int(body["total_copies"])
                    diff = new_total - book.total_copies
                    book.total_copies = new_total
                    book.available_copies = max(book.available_copies + diff, 0)
                except (TypeError, ValueError):
                    pass
            if "available_copies" in body:
                try:
                    book.available_copies = int(body["available_copies"])
                except (TypeError, ValueError):
                    pass
            storage.save_books(books)
            self._send_json(book.__dict__)
            return

        # No match
        self._send_json({"detail": "Not found", "code": "not_found"}, status=HTTPStatus.NOT_FOUND)

    def do_PATCH(self) -> None:
        # For simplicity, handle PATCH same as PUT
        self.do_PUT()

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        # Delete author
        base, res_id = self._parse_resource_path(path, "/api/authors/")
        if base.startswith("/api/authors/") and res_id is not None:
            user = self._get_auth_user()
            if not auth.require_role(user, ["LIBRARIAN", "ADMIN"]):
                self._send_json({"detail": "Forbidden", "code": "permission_denied"}, status=HTTPStatus.FORBIDDEN)
                return
            authors = storage.load_authors()
            if not any(a.id == res_id for a in authors):
                self._send_json({"detail": "Author not found", "code": "not_found"}, status=HTTPStatus.NOT_FOUND)
                return
            # Remove and save
            authors = [a for a in authors if a.id != res_id]
            storage.save_authors(authors)
            # 204 No Content
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        # Delete book
        base, res_id = self._parse_resource_path(path, "/api/books/")
        if base.startswith("/api/books/") and res_id is not None:
            user = self._get_auth_user()
            if not auth.require_role(user, ["LIBRARIAN", "ADMIN"]):
                self._send_json({"detail": "Forbidden", "code": "permission_denied"}, status=HTTPStatus.FORBIDDEN)
                return
            books = storage.load_books()
            book = next((b for b in books if b.id == res_id), None)
            if not book:
                self._send_json({"detail": "Book not found", "code": "not_found"}, status=HTTPStatus.NOT_FOUND)
                return
            books = [b for b in books if b.id != res_id]
            storage.save_books(books)
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        # Delete loan – not allowed via API (loans are only returned)
        self._send_json({"detail": "Not found", "code": "not_found"}, status=HTTPStatus.NOT_FOUND)


def run(server_class=HTTPServer, handler_class=APIServer, host: str = "127.0.0.1", port: int = 8000) -> None:
    server = server_class((host, port), handler_class)
    print(f"Library API server running on {host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run()