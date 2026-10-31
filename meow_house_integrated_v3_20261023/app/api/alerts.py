"""Rule-based alert API."""

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles, require_user
from app.config import settings
from app.database import get_db
from app.models import Alert, AlertHandling
from app.services.alert_service import evaluate_daily_rules
from app.services.governance_service import audit, ensure_pet_access


router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class AlertHandlingUpdate(BaseModel):
    status: str = Field(pattern="^(OPEN|ACKNOWLEDGED|RESOLVED)$")
    note: str | None = Field(default=None, max_length=1000)


@router.get("")
def list_alerts(member: dict = Depends(require_user), db: Session = Depends(get_db)):
    ensure_pet_access(db, member, settings.default_pet_id)
    alerts = db.scalars(
        select(Alert)
        .where(Alert.pet_id == settings.default_pet_id)
        .order_by(Alert.created_at.desc())
        .limit(30)
    ).all()
    result = []
    for alert in alerts:
        handling = db.get(AlertHandling, alert.id)
        result.append({
            "id": alert.id,
            "type": alert.type,
            "message": alert.message,
            "created_at": (
                alert.created_at
                if alert.created_at.tzinfo
                else alert.created_at.replace(tzinfo=timezone.utc)
            ).astimezone(timezone.utc).isoformat(),
            "resolved": alert.resolved,
            "handling_status": handling.status if handling else ("RESOLVED" if alert.resolved else "OPEN"),
            "handling_note": handling.note if handling else None,
            "handled_by": handling.handled_by if handling else None,
        })
    return result


@router.post("/evaluate", status_code=202)
def evaluate_alerts(
    member: dict = Depends(require_roles("CAREGIVER", "ADMIN")),
    db: Session = Depends(get_db),
):
    """Evaluate deterministic rules without mutating state from a GET request."""
    ensure_pet_access(db, member, settings.default_pet_id)
    alerts = evaluate_daily_rules(db, settings.default_pet_id)
    return {"evaluated": True, "active_rule_count": len(alerts)}


@router.patch("/{alert_id}")
def handle_alert(
    alert_id: int,
    payload: AlertHandlingUpdate,
    member: dict = Depends(require_roles("CAREGIVER")),
    db: Session = Depends(get_db),
):
    """Acknowledge or resolve an activity alert without making a diagnosis."""
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, "Alert not found")
    ensure_pet_access(db, member, alert.pet_id)
    handling = db.get(AlertHandling, alert.id)
    if handling is None:
        handling = AlertHandling(alert_id=alert.id)
        db.add(handling)
    handling.status = payload.status
    handling.note = payload.note.strip() if payload.note else None
    handling.handled_by = int(member["user_id"])
    alert.resolved = payload.status == "RESOLVED"
    audit(db, int(member["user_id"]), "ALERT_HANDLED", f"alert_id={alert.id}; status={payload.status}")
    db.commit()
    return {"id": alert.id, "status": handling.status, "resolved": alert.resolved}
