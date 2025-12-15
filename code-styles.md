# Python Code Style Guide
> FastAPI Backend Development Standards

**Version:** 1.0.0  
**Last Updated:** December 2025

---

## 🎯 Core Principles

This guide ensures consistency, maintainability, and security for Python backend development with FastAPI.

---

## 📝 Code Style Guidelines

### PEP 8 Compliance
- **MANDATORY:** Strictly adhere to PEP 8 standards for all Python code
- Use `ruff` for auto-formatting and linting

### Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| **Variables** | snake_case | `user_id`, `total_count` |
| **Functions** | snake_case | `get_user_by_id()`, `calculate_total()` |
| **Classes** | PascalCase | `UserService`, `DatabaseManager` |
| **Constants** | UPPER_SNAKE_CASE | `API_BASE_URL`, `MAX_RETRIES` |
| **Private** | _leading_underscore | `_internal_method()` |
| **Files** | snake_case | `user_service.py`, `auth_utils.py` |

### Documentation Requirements

**Every function and class MUST have a docstring:**
- Explain purpose clearly
- Document all parameters with types
- Document return value and type
- Include exceptions raised
- Add usage example for complex functions

**Format: Google Style Docstrings**

---

## 🔤 Type Hints (MANDATORY)

### Type Hinting Rules
- ✅ **ALWAYS** use type hints for function parameters
- ✅ **ALWAYS** specify return types (including `None`)
- ✅ Use `Optional[T]` for nullable values
- ✅ Use `Union[T1, T2]` for multiple possible types
- ✅ Use `List[T]`, `Dict[K, V]`, `Set[T]` for collections
- ❌ **NEVER** use bare `list`, `dict`, or `tuple` without type parameters

### Pydantic Models for FastAPI
- Use Pydantic `BaseModel` for all request/response schemas
- Use Pydantic validators for data validation
- Define clear field descriptions with `Field(description="...")`
- Use `ConfigDict` for model configuration

---

## 🏗️ Project Structure (FastAPI)

### Standard Directory Layout

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app initialization only
│   ├── core/
│   │   ├── config.py           # Settings with pydantic-settings
│   │   ├── security.py         # Auth, JWT, password hashing
│   │   └── database.py         # DB connection and session
│   ├── api/
│   │   └── v1/
│   │       ├── endpoints/      # API route handlers
│   │       │   ├── users.py
│   │       │   ├── auth.py
│   │       │   └── items.py
│   │       └── dependencies.py # Shared dependencies
│   ├── models/                 # SQLAlchemy/Tortoise ORM models
│   │   ├── user.py
│   │   └── item.py
│   ├── schemas/                # Pydantic request/response models
│   │   ├── user.py
│   │   └── item.py
│   ├── services/               # Business logic layer
│   │   ├── user_service.py
│   │   └── auth_service.py
│   ├── repositories/           # Data access layer (optional)
│   │   └── user_repository.py
│   └── utils/                  # Helper functions
│       ├── validators.py
│       └── formatters.py
├── tests/
│   ├── test_api.py
│   └── test_services.py
├── alembic/                    # Database migrations
├── requirements.txt
└── .env.example
```

### Module Responsibilities

**main.py** - Orchestration ONLY:
- ✅ Create FastAPI app instance
- ✅ Include routers
- ✅ Add middleware
- ✅ Configure CORS
- ❌ NO business logic
- ❌ NO route handlers
- ❌ NO data processing

**services/** - Business Logic:
- All business rules and algorithms
- Data transformation and processing
- Coordination between repositories
- Complex validation logic

**repositories/** - Data Access:
- Database queries only
- CRUD operations
- No business logic
- Return domain models

**endpoints/** - API Layer:
- HTTP request/response handling
- Input validation (via Pydantic)
- Call service layer
- Return appropriate HTTP status codes

---

## ⚠️ Error Handling Standards

### Exception Handling Rules

❌ **NEVER use bare except:**
```python
# BAD
try:
    result = dangerous_operation()
except:
    pass
```

✅ **ALWAYS catch specific exceptions:**
```python
# GOOD
try:
    result = dangerous_operation()
except ValueError as e:
    logger.error(f"Invalid value: {e}")
    raise
except KeyError as e:
    logger.error(f"Missing key: {e}")
    raise
```

### FastAPI Exception Handling

**Use HTTPException for API errors:**
- 400 Bad Request - Invalid input
- 401 Unauthorized - Missing/invalid auth
- 403 Forbidden - Insufficient permissions
- 404 Not Found - Resource doesn't exist
- 409 Conflict - Duplicate/conflict
- 422 Unprocessable Entity - Validation error
- 500 Internal Server Error - Server error

**Create custom exception handlers:**
- Define domain-specific exceptions
- Implement global exception handler
- Return consistent error format

### Graceful Failure

**Main execution MUST be wrapped:**
- Catch all unhandled exceptions at top level
- Log errors with full context
- Never show raw stack traces to users
- Return user-friendly error messages
- Exit gracefully with appropriate code

---

## 📊 Logging Standards

### Logging Rules

❌ **NEVER use print():**
- Not for debugging
- Not for info messages
- Not for errors
- **Use loguru library ALWAYS**

✅ **Use structured logging:**
- Import `loguru` module
- Configure logger with proper format
- Use appropriate log levels
- Include context in log messages

### Log Levels

| Level | When to Use | Example |
|-------|-------------|---------|
| **DEBUG** | Development debugging | Function entry/exit, variable values |
| **INFO** | General information | Request received, task completed |
| **WARNING** | Potential issues | Deprecated function used, retry attempt |
| **ERROR** | Error occurred | Failed operation, exception caught |
| **CRITICAL** | System failure | Database unreachable, service down |

### What to Log

✅ **DO log:**
- API requests (method, path, user)
- Authentication attempts
- Database operations
- External API calls
- Business logic decisions
- Errors with full context

❌ **DON'T log:**
- Passwords or secrets
- Personal identifiable information (PII)
- Credit card numbers
- API keys or tokens
- Session tokens

---

## 🔒 Security Non-Negotiables

### Secrets Management

❌ **NEVER hardcode secrets:**
```python
# FORBIDDEN
API_KEY = "sk-1234567890abcdef"
DATABASE_URL = "postgresql://user:pass@localhost/db"
JWT_SECRET = "my-secret-key"
```

✅ **ALWAYS use environment variables:**
```python
# REQUIRED
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    api_key: str
    database_url: str
    jwt_secret: str
    
    class Config:
        env_file = ".env"
```

### Input Validation

**MANDATORY for all user inputs:**
- ✅ Validate CLI arguments with `argparse` or `typer`
- ✅ Validate HTTP requests with Pydantic schemas
- ✅ Sanitize all string inputs
- ✅ Validate file uploads (type, size, content)
- ✅ Use parameterized queries for database (prevent SQL injection)

### Forbidden Operations

❌ **NEVER use:**
- `eval()` - Arbitrary code execution risk
- `exec()` - Arbitrary code execution risk
- `__import__()` with user input
- `pickle.loads()` with untrusted data
- String concatenation for SQL queries

---

## 🗄️ Database Best Practices

### ORM Usage

**Use SQLAlchemy or Tortoise ORM:**
- Define models in `models/` directory
- Use declarative base for SQLAlchemy
- Always use type hints on model fields
- Define relationships explicitly

### Migration Management

**Use Alembic for migrations:**
- ✅ Create migration for EVERY schema change
- ✅ Test migrations in development first
- ✅ Include both upgrade and downgrade
- ❌ NEVER manually ALTER database
- ❌ NEVER skip migration files

### Query Safety

**Prevent SQL Injection:**
- ✅ Use ORM query methods
- ✅ Use parameterized queries
- ❌ NEVER use f-strings with SQL
- ❌ NEVER concatenate user input into queries

### Database Sessions

**FastAPI Dependency Pattern:**
- Use `Depends()` for database session
- Ensure sessions are closed after request
- Use context managers for transactions
- Handle connection errors gracefully

---

## 🧪 Testing Requirements

### Test Structure

**Co-locate tests with source:**
- Unit tests: `tests/test_services.py`
- Integration tests: `tests/test_api.py`
- Use pytest framework
- Use fixtures for common setup

### Test Coverage Goals

| Component | Minimum Coverage |
|-----------|------------------|
| **Services** | 90%+ |
| **Repositories** | 80%+ |
| **API Endpoints** | 85%+ |
| **Utilities** | 90%+ |

### Testing Best Practices

✅ **DO:**
- Mock external dependencies (APIs, databases)
- Test happy path and error cases
- Test edge cases and boundary conditions
- Use descriptive test names
- Keep tests independent

❌ **DON'T:**
- Test implementation details
- Create interdependent tests
- Use real database in unit tests
- Skip error case testing

---

## 📦 Dependency Management

### Requirements Files

**Use multiple requirements files:**
- `requirements.txt` - Production dependencies
- `requirements-dev.txt` - Development tools
- `requirements-test.txt` - Testing dependencies

**Pin versions explicitly:**
- ✅ `fastapi==0.109.0`
- ❌ `fastapi` (unpinned)
- ❌ `fastapi>=0.100.0` (too loose)

### Adding Dependencies

**Before adding a package, verify:**
1. Is it actively maintained? (updated < 6 months)
2. Does it have good documentation?
3. Are there known vulnerabilities? (`pip-audit`)
4. What's the license?
5. Can we use existing dependency instead?

---

## 🚀 FastAPI Specific Guidelines

### API Design

**RESTful Conventions:**
- `GET /users` - List users
- `GET /users/{id}` - Get single user
- `POST /users` - Create user
- `PUT /users/{id}` - Full update
- `PATCH /users/{id}` - Partial update
- `DELETE /users/{id}` - Delete user

### Path Parameters vs Query Parameters

**Path parameters** - Resource identification:
- `/users/{user_id}`
- `/posts/{post_id}/comments/{comment_id}`

**Query parameters** - Filtering/pagination:
- `/users?role=admin&status=active`
- `/posts?page=2&limit=20&sort=-created_at`

### Response Models

**Use Pydantic response models:**
- Define clear response schemas
- Exclude sensitive fields (`password_hash`)
- Use `response_model` parameter
- Include proper HTTP status codes

### Async/Await

**Use async for I/O operations:**
- Database queries
- External API calls
- File operations
- Network requests

**Don't use async for:**
- CPU-bound operations
- Synchronous libraries
- Simple calculations

---

## 🎨 Code Quality Tools

### Required Tools

**Formatting & Linting:**
- `ruff` - Auto-formatter and linter

### Pre-commit Hooks

**Install pre-commit:**
```
.pre-commit-config.yaml should include:
- ruff
```

---

## 📚 Resources

**Official Documentation:**
- FastAPI: https://fastapi.tiangolo.com
- Pydantic: https://docs.pydantic.dev
- SQLAlchemy: https://docs.sqlalchemy.org
- PEP 8: https://pep8.org
- Ruff: https://docs.astral.sh/ruff

---

## 🔄 Updates

This document is living documentation. Update when:
- New patterns emerge
- Security issues discovered
- Team conventions change
- FastAPI updates require changes

---

**Remember:** These rules ensure code quality, security, and maintainability. Follow them strictly for consistent, professional Python backend development.