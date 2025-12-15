# Python Code Style Guide
> FastAPI Backend Development Standards

**Version:** 2.0.0
**Last Updated:** December 2025

---

## 🎯 Core Principles

This guide ensures consistency, maintainability, and scalability for Python backend development with FastAPI. We adhere to a **Layered Architecture (Route-Service-Repository)** pattern to separate concerns and ensure testability.

---

## 🏗️ Architecture Standard (Route-Service-Domain)

We strictly follow a layered architecture to separate concerns.

### 1. Layers Overview

| Layer | Responsibility | Allowed Dependencies | Examples |
|-------|----------------|----------------------|----------|
| **Presentation (Route)** | HTTP handling, Request parsing, Response formatting | Service Layer | `src/api/v1/endpoints` |
| **Application (Service)** | Business Logic, Orchestration, Transactions | Repository, Domain, Utils | `src/services` |
| **Data (Repository)** | Database access, CRUD, External API calls | Domain, DB Session | `src/repositories` |
| **Domain (Core)** | Data Models (ORM), Schemas (Pydantic), Exceptions | None (Pure Python) | `src/schemas`, `src/database/models` |

### 2. Directory Structure

```
src/
├── api/
│   └── v1/
│       └── endpoints/      # ❌ NO Business Logic, ❌ NO DB Queries
├── services/               # ✅ Business Logic, ✅ Transaction Mgmt
├── repositories/           # ✅ Database Queries, ✅ External API Calls
├── schemas/                # ✅ Pydantic Models (Data Transfer Objects)
├── database/
│   └── models/             # ✅ SBOM / ORM Models
```

### 3. Layer Rules

#### **Presentation Layer (Routes)**
- **Role:** Handle HTTP methods (GET, POST, etc.)
- **Responsibility:**
    - Validate inputs (using Pydantic)
    - Call the Service Layer
    - Handle Service Exceptions and map to HTTP Status Codes
- **Forbidden:**
    - Writing SQL/ORM queries (`select(...)`)
    - Performing business calculations
    - Calling 3rd party APIs directly

#### **Service Layer**
- **Role:** The "Brain" of the application
- **Responsibility:**
    - Execute business rules (e.g., "User must be admin to delete")
    - Orchestrate multiple repositories (e.g., "Get User -> Create Log -> Send Email")
    - Manage Database Transactions (Commit/Rollback) using dependency injection
- **Forbidden:**
    - Returning HTTP Responses (return Pydantic models or dicts instead)
    - Handling HTTP specific errors (raise custom Business Exceptions instead)

#### **Repository Layer**
- **Role:** The "Librarian"
- **Responsibility:**
    - Abstract the database implementation
    - Provide clean methods (`get_by_id`, `create`, `delete`)
    - Handle low-level DB errors
- **Forbidden:**
    - Business logic validation

---

## 📝 Code Style Guidelines

### PEP 8 Compliance
- **MANDATORY:** Strictly adhere to PEP 8 standards
- Use `ruff` for auto-formatting and linting

### Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| **Variables** | snake_case | `user_id`, `total_count` |
| **Functions** | snake_case | `get_user_by_id()` |
| **Classes** | PascalCase | `UserService`, `UserRepository` |
| **Constants** | UPPER_SNAKE_CASE | `API_BASE_URL` |
| **Files** | snake_case | `user_service.py` |

---

## ⚠️ Error Handling Standards

### Service Layer Exceptions
Define custom exceptions in `src/core/exceptions.py`:
```python
class UserNotFoundError(Exception):
    pass
```

### Route Layer Handling
Map service exceptions to HTTP exceptions:
```python
# Service
if not user:
    raise UserNotFoundError("User 123 not found")

# Route
try:
    service.get_user(123)
except UserNotFoundError as e:
    raise HTTPException(status_code=404, detail=str(e))
```

---

## 🔤 Type Hints (MANDATORY)

- ✅ **ALWAYS** use type hints for function parameters and return types
- ✅ Use `src/schemas` (Pydantic) for data transfer between layers
- ❌ **NEVER** pass ORM models directly to the frontend (always convert to Pydantic schema)

---

## 🧪 Testing Requirements

- **Unit Tests (`tests/unit`)**: Test Services and Repositories in isolation (mock DB).
- **Integration Tests (`tests/integration`)**: Test API endpoints with a test database.
- **Coverage**: Aim for >90% coverage on Service logic.

---

**Remember:** Clean architecture makes features **cheap** to add and bugs **easy** to find.