"""Current cat profile API."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.api.dependencies import require_user
from app.database import get_db
from app.models.pet import Pet
from app.services.governance_service import ensure_pet_access


router = APIRouter(prefix="/api/pets", tags=["pets"])


@router.get("/current")
def current_pet(member: dict = Depends(require_user), db: Session = Depends(get_db)):
    pet = ensure_pet_access(db, member, settings.default_pet_id)
    if not pet:
        raise HTTPException(404, "Current pet not found")
    return {
        "id": pet.id,
        "name": pet.name,
        "gender": pet.gender,
        "age": pet.age,
        "breed": pet.breed,
        "weight": pet.weight,
        "personality": pet.personality,
        "food_notes": pet.food_notes,
        "care_notes": pet.care_notes,
        "medical_notes": pet.medical_notes,
    }

