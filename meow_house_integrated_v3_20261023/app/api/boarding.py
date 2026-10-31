"""Current boarding stay API."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_user
from app.config import settings
from app.database import get_db
from app.models.boarding import BoardingOrder, CatHouse
from app.services.governance_service import ensure_pet_access


router = APIRouter(prefix="/api/boarding", tags=["boarding"])


@router.get("/current")
def current_boarding(member: dict = Depends(require_user), db: Session = Depends(get_db)):
    ensure_pet_access(db, member, settings.default_pet_id)
    row = db.execute(
        select(BoardingOrder, CatHouse)
        .join(CatHouse, BoardingOrder.cat_house_id == CatHouse.id)
        .where(
            BoardingOrder.pet_id == settings.default_pet_id,
            BoardingOrder.status == "CHECKED_IN",
        )
    ).first()
    if not row:
        return {"status": "NOT_CHECKED_IN"}
    order, house = row
    return {
        "id": order.id,
        "status": order.status,
        "start_date": order.start_date.isoformat(),
        "end_date": order.end_date.isoformat(),
        "room_number": house.room_number,
    }

