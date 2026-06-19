from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field

from app.auth import UserResponse, requires_role
from app.models import User

router = APIRouter(prefix="/users", tags=["users"])


class UserProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None


@router.get("/me", response_model=UserResponse)
def get_profile(current_user: Annotated[User, Depends(requires_role("admin", "doctor", "researcher", "viewer", "super_admin"))]):
    return current_user
