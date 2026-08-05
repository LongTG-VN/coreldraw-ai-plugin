# PYTHON Rules

# Python Developer Guidelines

## Naming Conventions
- Use `snake_case` for modules, functions, variables, and test names.
- Use `PascalCase` for classes and exceptions.
- Name predicates with a clear boolean meaning such as `is_ready`.
- Follow PEP 8 naming conventions:
- PascalCase for classes

## Project Structure
- Keep importable code in a package and tests in a dedicated `tests/` tree.
- Keep entry points thin and move reusable logic into focused modules.
- Define dependencies and supported Python versions in project metadata.
- Use src-layout with `src/your_package_name/`
- Place tests in `tests/` directory parallel to `src/`
- Keep configuration in `config/` or as environment variables
- Store requirements in `requirements.txt` or `pyproject.toml`
- Place static files in `static/` directory
- Use `templates/` for Jinja2 templates
- Use isort for import sorting
- Import types from `typing` module
- Use Flask factory pattern
- Organize routes using Blueprints
- Use Flask-SQLAlchemy for database
- Implement proper error handlers

## Best Practices
- Prefer explicit data flow and small functions over hidden global state.
- Catch only errors that can be handled meaningfully.
- Add type hints at public boundaries and validate untrusted input.
- Use context managers for files, locks, and network resources.
- Test normal behavior, boundaries, failures, and cleanup.
- Never place credentials in source code or committed configuration.
- Follow Black code formatting
- snake_case for functions and variables
- UPPER_CASE for constants
- Maximum line length of 88 characters (Black default)
- Use absolute imports over relative imports
- Use type hints for all function parameters and returns
- Use `Optional[Type]` instead of `Type | None`
- Use `TypeVar` for generic types
- Define custom types in `types.py`
- Use `Protocol` for duck typing
- Use SQLAlchemy ORM
- Implement database migrations with Alembic
- Use proper connection pooling
- Define models in separate modules
- Implement proper relationships
- Use proper indexing strategies
- Use Flask-Login for session management
- Implement Google OAuth using Flask-OAuth
- Hash passwords with bcrypt


---

# FASTAPI Rules

# Fastapi Developer Guidelines

## Naming Conventions
- Use nouns for resources and explicit verbs only for non-resource actions.
- Name request and response models by their API role.
- Use `snake_case` for Python identifiers and stable operation IDs.

## Project Structure
- Keep route handlers thin and move domain logic into services.
- Separate API schemas from persistence models.
- Centralize dependencies for authentication, authorization, and transactions.
- Use proper directory structure
- Implement proper module organization
- Use proper dependency injection
- Keep routes organized by domain
- Implement proper middleware
- Use proper configuration management
- ONLY layer allowed to import sqlalchemy
- ONLY layer allowed to import httpx directly
- from app.models.user import User inside a service → return domain types from repo

## Best Practices
- Validate all external input with explicit schemas.
- Return stable error shapes without leaking internal exceptions.
- Bound request sizes, timeouts, and downstream retries.
- Use lifespan hooks for shared clients and cleanup.
- Test authorization and failure behavior as well as happy paths.
- Keep blocking work out of asynchronous handlers.
- Use proper HTTP methods
- Implement proper status codes
- Use proper request/response models
- Implement proper validation
- Use proper error handling
- Document APIs with OpenAPI
- Use Pydantic models
- Use proper type hints
- Keep models organized
- Use proper inheritance
- Implement proper serialization
- Use proper ORM (SQLAlchemy)
- Implement proper migrations
- Use proper connection pooling
- Implement proper transactions
- Use proper query optimization
- Handle database errors properly
- Implement proper JWT authentication
- Use proper password hashing
