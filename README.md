# 🚀 TaskFlow Backend API

![CI](https://github.com/Joaovictoreth1/taskflow-backend-api/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)
![License](https://img.shields.io/badge/License-MIT-green)

A professional RESTful API for task and project management, built with **FastAPI**, **SQLAlchemy**, and **Pydantic v2**.

## 📐 Architecture

```text
app/
├── __init__.py          # Package init
├── main.py              # FastAPI app, CORS, rate limiting, all routes
├── database.py          # SQLAlchemy engine & session (SQLite / PostgreSQL)
├── models.py            # ORM models with relationships
├── schemas.py           # Pydantic v2 request/response schemas
└── crud.py              # Database operations (create, read, update, delete)

tests/
└── test_api.py          # 30+ automated tests with pytest

.github/workflows/
└── ci.yml               # GitHub Actions CI pipeline
```

## 🗃️ Data Models

| Relationship | Models | Type |
|---|---|---|
| Student ↔ Profile | `students` ↔ `profiles` | **One-to-One** |
| Project → Tasks | `projects` → `tasks` | **One-to-Many** |

### Task Statuses
- `todo` — Default
- `in_progress` — Work in progress
- `done` — Completed

## 🛠️ Setup

### Prerequisites
- Python 3.11+
- pip

### Installation

```bash
# Clone the repository
git clone https://github.com/Joaovictoreth1/taskflow-backend-api.git
cd taskflow-backend-api

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (macOS/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

```bash
# Copy the environment example
cp .env.example .env

# Edit .env to configure your database (default: SQLite)
```

### Run the server

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`.

## 📖 API Documentation

| Docs | URL |
|---|---|
| **Swagger UI** | [http://localhost:8000/docs](http://localhost:8000/docs) |
| **ReDoc** | [http://localhost:8000/redoc](http://localhost:8000/redoc) |

## 🔗 API Endpoints

### Health
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Root health check |
| `GET` | `/health` | Health status |

### Students
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/students` | Create a student |
| `GET` | `/students` | List students (paginated) |
| `GET` | `/students/{id}` | Get student by ID |
| `PATCH` | `/students/{id}` | Update student |
| `DELETE` | `/students/{id}` | Delete student |

### Profiles (1:1 with Student)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/students/{id}/profile` | Create profile |
| `PATCH` | `/students/{id}/profile` | Update profile |

### Projects
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/projects` | Create a project |
| `GET` | `/projects` | List projects (paginated) |
| `GET` | `/projects/{id}` | Get project with tasks |
| `PATCH` | `/projects/{id}` | Update project |
| `DELETE` | `/projects/{id}` | Delete project (cascades tasks) |

### Tasks
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/projects/{id}/tasks` | Create task in project |
| `GET` | `/projects/{id}/tasks` | List tasks by project |
| `GET` | `/tasks/{id}` | Get task by ID |
| `PATCH` | `/tasks/{id}` | Update task |
| `DELETE` | `/tasks/{id}` | Delete task |

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --tb=short
```

## 🔒 Features

- **CORS** — Cross-Origin Resource Sharing enabled for all origins
- **Rate Limiting** — Powered by SlowAPI (30-60 req/min per endpoint)
- **Validation** — Strict Pydantic v2 schemas with email, length, and enum validation
- **Cascade Deletes** — Deleting a Student removes their Profile; deleting a Project removes all Tasks
- **Pagination** — `skip` and `limit` query params on list endpoints
- **CI/CD** — GitHub Actions runs tests on every push/PR

## 📄 License

MIT © João Victor
