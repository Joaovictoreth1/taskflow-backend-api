# 🚀 TaskFlow Backend API

![CI](https://github.com/Joaovictoreth1/taskflow-backend-api/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-red?logo=sqlalchemy)
![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063?logo=pydantic)
![JWT Auth](https://img.shields.io/badge/Auth-JWT%20%2B%20Bcrypt-orange?logo=jsonwebtokens)
![License](https://img.shields.io/badge/License-MIT-green)

A production-ready RESTful API for task and project management, built with **FastAPI**, **SQLAlchemy 2.0**, **Pydantic v2**, **JWT Authentication (OAuth2 Bearer)**, **Alembic migrations**, and **Docker**.

---

## 📐 Architecture

```text
taskflow-backend-api/
├── alembic/                 # Database migrations with Alembic
│   ├── versions/            # Migration revisions
│   └── env.py               # Migration runtime configuration
├── app/
│   ├── __init__.py          # Package init
│   ├── main.py              # FastAPI app, CORS, SlowAPI rate limiting, routes
│   ├── database.py          # SQLAlchemy engine & session (SQLite / PostgreSQL)
│   ├── models.py            # Relational ORM models (User, Student, Profile, Project, Task)
│   ├── schemas.py           # Pydantic v2 schemas with strict validation & pagination
│   ├── crud.py              # Isolated database operations
│   ├── security.py          # Password hashing (bcrypt) & JWT token lifecycle
│   └── dependencies.py      # OAuth2 Bearer user authentication dependencies
├── tests/
│   ├── conftest.py          # Shared test fixtures & SQLite in-memory test database
│   ├── test_api.py          # Base CRUD & relational integration tests (42 tests)
│   ├── test_auth.py         # JWT registration, login, protected routes (14 tests)
│   ├── test_tasks_advanced.py # Priorities, due dates, filtering & envelope pagination (15 tests)
│   └── test_analytics_and_comments.py # Analytics, task comments, CSV export & password updates (16 tests)
├── .github/workflows/
│   └── ci.yml               # Automated matrix CI testing across Python 3.11 & 3.12
├── Dockerfile               # Multi-stage production container image
├── docker-compose.yml       # Full stack: FastAPI + PostgreSQL 16
├── requirements.txt         # Pinned production & test dependencies
├── alembic.ini              # Alembic environment configuration
├── .env.example             # Example environment variables
├── .gitignore               # Strict git ignore patterns
└── README.md                # Project documentation
```

---

## 🗃️ Data Models & Relationships

| Relationship | Models | Cardinality | Key Fields |
|---|---|---|---|
| User ➔ Projects | `users` ➔ `projects` | **One-to-Many** | `username`, `email`, `hashed_password`, `is_active` |
| Student ↔ Profile | `students` ↔ `profiles` | **One-to-One** | `name`, `email`, `bio`, `avatar_url` |
| Project ➔ Tasks | `projects` ➔ `tasks` | **One-to-Many** | `name`, `description`, `owner_id` |
| Task ➔ Comments | `tasks` ➔ `task_comments` | **One-to-Many** | `author_name`, `content`, `user_id` |

### Task Attributes
- **Status:** `todo` (default), `in_progress`, `done`
- **Priority:** `low`, `medium` (default), `high`, `urgent`
- **Due Date:** Optional ISO 8601 datetime (`due_date`)

---

## 🔐 Authentication & Security

- **Password Hashing:** Native `bcrypt` with automatic 12-round salt and 72-byte truncation safeguard.
- **Access Tokens:** Signed HMAC-SHA256 (HS256) JSON Web Tokens with configurable expiration.
- **Route Protection:** `Depends(get_current_active_user)` dependency enforcing valid Bearer tokens.
- **Rate Limiting:** `SlowAPI` integration protecting public and auth endpoints against brute force attacks.

---

## 🛠️ Quickstart

### 1. Local Environment Setup

```bash
# Clone the repository
git clone https://github.com/Joaovictoreth1/taskflow-backend-api.git
cd taskflow-backend-api

# Create & activate virtual environment
python -m venv venv
venv\Scripts\activate       # Windows
source venv/bin/activate    # Linux / macOS

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
```

### 2. Database Migrations

```bash
# Apply migrations to head
alembic upgrade head
```

### 3. Run Development Server

```bash
uvicorn app.main:app --reload --port 8000
```

- Interactive OpenAPI Swagger UI: `http://localhost:8000/docs`
- ReDoc Documentation: `http://localhost:8000/redoc`

---

## 🐳 Docker & Docker Compose

Run the complete production stack (FastAPI backend + PostgreSQL 16) with a single command:

```bash
docker compose up -d --build
```

The API will be available at `http://localhost:8000` with PostgreSQL connected on port `5433`.

---

## 🧪 Automated Testing

The project includes **71 comprehensive integration tests** covering all endpoints, authentication flows, relational cascades, rate limit bypass in test mode, and pagination:

```bash
pytest tests/ -v
```

---

## 📡 API Reference Summary

### Authentication
- `POST /auth/register` — Register a new account (`username`, `email`, `password`)
- `POST /auth/login` — Login and receive a JWT Bearer token
- `GET /auth/me` — Retrieve current authenticated user profile

### Projects & Pagination
- `POST /projects` — Create project (associates with authenticated user if token present)
- `GET /projects` — List projects (with search query `?search=keyword`)
- `GET /projects/paginated` — Paginated envelope (`?page=1&size=10`)
- `GET /projects/{id}` — Get project details including associated tasks
- `PATCH /projects/{id}` — Update project
- `DELETE /projects/{id}` — Delete project (cascades to associated tasks)

### Tasks & Filtering
- `POST /projects/{id}/tasks` — Create task with status, priority, and due date
- `GET /tasks` — Multi-criteria filter (`?status=done&priority=urgent&search=auth&page=1&size=10`)
- `GET /tasks/{id}` — Get single task
- `PATCH /tasks/{id}` — Update task status, priority, or due date
- `DELETE /tasks/{id}` — Delete task

### Students & Profiles (1:1)
- `POST /students` — Create student (optional nested profile)
- `GET /students` — List students
- `GET /students/{id}` — Get student with profile
- `POST /students/{id}/profile` — Create profile for student
- `PATCH /students/{id}/profile` — Update profile

---

## 📄 License
This project is open-sourced under the MIT License.
