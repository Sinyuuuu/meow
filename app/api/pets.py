"""Current cat profile read, edit, and photo APIs."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles, require_user
from app.config import BASE_DIR, settings
from app.database import get_db
from app.models.pet import Pet
from app.services.governance_service import audit, ensure_pet_access


router = APIRouter(prefix="/api/pets", tags=["pets"])
PHOTO_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAX_PHOTO_BYTES = 5 * 1024 * 1024


class PetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    gender: str | None = Field(default=None, max_length=20)
    age: int | None = Field(default=None, ge=0, le=40)
    breed: str | None = Field(default=None, max_length=80)
    weight: float | None = Field(default=None, ge=0.1, le=40)
    personality: str | None = Field(default=None, max_length=1000)
    food_notes: str | None = Field(default=None, max_length=2000)
    care_notes: str | None = Field(default=None, max_length=2000)
    medical_notes: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


def _serialize(pet: Pet) -> dict:
    return {
        "id": pet.id, "name": pet.name, "photo": pet.photo, "gender": pet.gender,
        "age": pet.age, "breed": pet.breed, "weight": pet.weight,
        "personality": pet.personality, "food_notes": pet.food_notes,
        "care_notes": pet.care_notes, "medical_notes": pet.medical_notes,
    }


@router.get("/current")
def current_pet(member: dict = Depends(require_user), db: Session = Depends(get_db)):
    pet = ensure_pet_access(db, member, settings.default_pet_id)
    if not pet:
        raise HTTPException(404, "Current pet not found")
    return _serialize(pet)


@router.patch("/current")
def update_current_pet(
    payload: PetUpdate,
    member: dict = Depends(require_roles("OWNER")),
    db: Session = Depends(get_db),
):
    pet = ensure_pet_access(db, member, settings.default_pet_id)
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(400, "No fields were supplied")
    for key, value in values.items():
        if isinstance(value, str):
            value = value.strip() or None
        setattr(pet, key, value)
    audit(db, int(member["user_id"]), "PET_PROFILE_UPDATED", f"pet_id={pet.id}; fields={','.join(values)}")
    db.commit()
    db.refresh(pet)
    return _serialize(pet)


@router.post("/current/photo", status_code=201)
async def upload_current_pet_photo(
    photo: UploadFile = File(...),
    member: dict = Depends(require_roles("OWNER")),
    db: Session = Depends(get_db),
):
    pet = ensure_pet_access(db, member, settings.default_pet_id)
    suffix = PHOTO_TYPES.get(photo.content_type or "")
    if suffix is None:
        raise HTTPException(415, "Photo must be JPEG, PNG, or WebP")
    content = await photo.read(MAX_PHOTO_BYTES + 1)
    if not content:
        raise HTTPException(400, "Photo is empty")
    if len(content) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "Photo must be 5 MB or smaller")
    upload_dir = BASE_DIR / "app" / "static" / "uploads" / "pets"
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"pet_{pet.id}_{uuid4().hex}{suffix}"
    destination = upload_dir / filename
    destination.write_bytes(content)
    pet.photo = f"/static/uploads/pets/{filename}"
    audit(db, int(member["user_id"]), "PET_PHOTO_UPDATED", f"pet_id={pet.id}")
    db.commit()
    return {"photo": pet.photo}
