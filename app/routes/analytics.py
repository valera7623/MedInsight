from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.services.dashboard import get_dashboard_data

router = APIRouter(prefix="/analytics", tags=["analytics"])


class RecentPatient(BaseModel):
    id: int
    first_name: str
    last_name: str
    middle_name: str | None
    birth_date: str
    gender: str
    created_at: str


class DashboardResponse(BaseModel):
    total_patients: int
    total_documents: int
    diagnoses: dict[str, int]
    medications: dict[str, int]
    recent_patients: list[RecentPatient]


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    return get_dashboard_data(db, current_user.id)
