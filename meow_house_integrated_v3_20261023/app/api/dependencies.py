"""Shared authentication and role guards for private API routes."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.services.governance_service import is_user_active


def require_user(request: Request, db: Session = Depends(get_db)) -> dict[str, object]:
    """Require an authenticated member session for private cat data."""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    user = db.get(User, int(user_id))
    if user is None or not is_user_active(db, user.id):
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account unavailable")
    return {"user_id": user.id, "name": user.name, "role": user.role}


def require_roles(*allowed_roles: str) -> Callable[..., dict[str, object]]:
    """Build a dependency that restricts an action to explicit member roles."""
    allowed = set(allowed_roles)

    def guard(member: dict = Depends(require_user)) -> dict[str, object]:
        if member.get("role") not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role",
            )
        return member

    return guard

