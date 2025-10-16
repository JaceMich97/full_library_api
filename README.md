# Library Management System API

This project implements a simple REST‑like API for managing a library’s
catalogue, users and loans.  It follows the specification defined in
the capstone project documents and is built using only Python’s
standard library.  All data is stored on disk in JSON files under
`full_library_api/data/`, so nothing is lost between runs.

## Features

- **Authentication** – users can register, log in and log out.  Passwords
  are hashed using SHA‑256 and a simple token system is used for
  authentication.  Three roles are supported: `MEMBER`, `LIBRARIAN`
  and `ADMIN`.
- **Authors** – CRUD endpoints allow listing, creating, updating and
  deleting authors.  Searching by name, ordering, pagination and
  role‑based permissions are implemented.
- **Books** – CRUD endpoints allow listing, creating, updating and
  deleting books.  Books can be filtered by author and publication
  year, searched by title or author name, ordered by various fields,
  and paginated.  Available copies are automatically adjusted when
  loans are created or returned.
- **Loans** – members can borrow and return books; librarians and
  admins can view and manage all loans.  Business rules enforce that
  a user cannot borrow a book if no copies are available and cannot
  hold multiple active loans for the same book.  Loans record
  borrowed and due dates and support overdue filtering.  Only the
  borrower or staff can view a given loan.

## Running the server

No external dependencies are required.  To start the server, run the
following command from the `full_library_api` directory:

```bash
python app.py
```

By default the server listens on `127.0.0.1:8000`.  You can modify
the `run` function in `app.py` to bind to a different host or port.

## API Endpoints

All endpoints are prefixed with `/api/` and accept/return JSON.

### Authentication

- **POST /api/auth/register/** – create a new user.  Request body
  requires `username`, `email` and `password`.  Optional `role` can
  be `MEMBER`, `LIBRARIAN` or `ADMIN`.  Returns a summary of the
  created user.
- **POST /api/auth/login/** – obtain a token.  Body requires
  `username` and `password`.  Returns `{ "token": "..." }` on
  success.
- **POST /api/auth/logout/** – invalidate the current token.  The
  header `Authorization: Token <token>` must be provided.

### Authors

- **GET /api/authors/** – list authors.  Supports optional
  query parameters:
  - `search=` – substring search on author names.
  - `ordering=` – order by `id` or `name` (`-name` for descending).
  - `page=` and `page_size=` – pagination.
- **POST /api/authors/** – create a new author (requires LIBRARIAN or
  ADMIN).  Body: `{ "name": "Author Name" }`.
- **GET /api/authors/{id}/** – retrieve a single author by ID.
- **PUT/PATCH /api/authors/{id}/** – update an author’s name
  (requires LIBRARIAN or ADMIN).  Body may include `name`.
- **DELETE /api/authors/{id}/** – delete an author (requires
  LIBRARIAN or ADMIN).

### Books

- **GET /api/books/** – list books with optional filtering,
  search, ordering and pagination.  Query parameters:
  - `search=` – substring search in book titles and author names.
  - `author=` – filter by author ID.
  - `publication_year=` – filter by year.
  - `ordering=` – order by `id`, `title`, `publication_year` or
    `author` (prefix with `-` for descending).
  - `page=` and `page_size=` – pagination.
- **POST /api/books/** – create a new book (requires LIBRARIAN or
  ADMIN).  Body requires `title`, `publication_year`, `isbn`,
  `author` (author ID), `total_copies` and optional `available_copies`.
- **GET /api/books/{id}/** – retrieve a book by ID.
- **PUT/PATCH /api/books/{id}/** – update book fields (requires
  LIBRARIAN or ADMIN).  Fields may include `title`,
  `publication_year`, `isbn`, `author`, `total_copies` and
  `available_copies`.
- **DELETE /api/books/{id}/** – delete a book (requires LIBRARIAN or
  ADMIN).

### Loans

- **POST /api/loans/borrow/** – borrow a book (requires authentication).
  Body: `{ "book_id": 12 }`.  Creates a loan if a copy is available
  and returns the loan object.
- **POST /api/loans/return/** – return a book (requires authentication).
  Body may include `loan_id` or `book_id`.  Only the borrower or staff
  can perform this action.
- **GET /api/loans/mine/** – list loans belonging to the current user.
  Supports `status=borrowed|returned`, `overdue=true`, `ordering=` and
  pagination (`page`, `page_size`).
- **GET /api/loans/** – list all loans (requires LIBRARIAN or ADMIN).
  Supports the same filters as `/api/loans/mine/` plus `user_id=` to
  filter by user.
- **GET /api/loans/{id}/** – retrieve a specific loan.  Only the
  borrower or staff may access the loan.

## Data Storage

Data is persisted in JSON files under the `data/` directory.  On the
first run these files are created automatically.  You can remove
them to reset the system.  The `tokens.json` file stores active
authentication tokens.

## Testing

While no automated tests are included, the code is modular and
structured to facilitate unit testing.  You can use tools like
`pytest` to test the individual functions in `auth.py`,
`storage.py`, `utils.py` and the request handler methods in
`app.py`.
