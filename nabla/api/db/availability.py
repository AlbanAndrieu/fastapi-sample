"""Request-time guard for routes that need the optional PostgreSQL database."""

from fastapi import HTTPException, Request, status


def require_database(request: Request) -> None:
    """Answer 503 instead of 500 when the lifespan started without PostgreSQL."""
    if getattr(request.app.state, "database_available", True) is False:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL is not available; this route needs the database",
        )
