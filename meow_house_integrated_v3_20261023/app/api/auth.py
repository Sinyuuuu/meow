"""Prototype member sign-in routes."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.services.auth_service import verify_password
from app.services.governance_service import audit, is_user_active


router = APIRouter()


@router.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """Authenticate a seeded member and store only basic identity in the session."""
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if not user or not verify_password(password, user.password_hash) or not is_user_active(db, user.id):
        request.session["login_error"] = "帳號或密碼不正確"
        return RedirectResponse("/login", status_code=303)
    audit(db, user.id, "LOGIN", f"role={user.role}")
    db.commit()
    request.session.clear()
    request.session.update({"user_id": user.id, "name": user.name, "role": user.role})
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

