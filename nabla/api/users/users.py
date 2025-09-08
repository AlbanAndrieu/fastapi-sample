import asyncio
import random

from sqlalchemy import Column, Integer, String, Boolean
from pydantic import BaseModel

from sqlalchemy.orm import declarative_base
from fastapi import APIRouter, HTTPException, Depends
from fastapi_cache.decorator import cache

from nabla.utils.logger import logger
from nabla.utils.prometheus import USER_REGISTRATIONS
from nabla.db import get_db


router = APIRouter(prefix="/test")

Base = declarative_base()


class UserEvent(BaseModel):
    def __init__(self, name = "Alban Andrieu", email = "alban.andrieu@nabla.io", password = "password"):
        self.name = name
        self.email = email
        self.password = password
        self.active = True
        self.role = "admin"
        self.permissions = ["read", "write"]
        self.groups = ["admin"]
        self.phone = "0695435353"
        self.address = "11 terrasse de l'université"
        self.city = "Paris"
        self.state = "FR"
        self.zip = "92000"
        self.country = "France"
        # created_at: str # Remove unused fields like "created_at_timestamp" for the frontend
        # updated_at: str
        # last_login: str
        # last_login_ip: str
        # last_login_device: str
        # last_login_location: str
        # last_login_browser: str
        # last_login_os: str

class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    password = Column(String, nullable=False)
    active = Column(Boolean, nullable=False)
    role = Column(String, nullable=False)
    permissions = Column(String, nullable=False)
    groups = Column(String, nullable=False)


    def __str__(self):
        return f"User ID : {self.id}\tName : {self.name}\tEmail : {self.email}\tPassword : {self.password}\tActive : {self.active}\tRole : {self.role}\tPermissions : {self.permissions}\tGroups : {self.groups}\tCreated Date : {self.timestamp}"


@router.get("/users/{user_id}", response_model=UserEvent, operation_id="get_user_info")
@cache(expire=300)  # Cache for 5 minutes to avoid repeated execution of complex SQL
async def get_user(user_id: int, db=Depends(get_db)):
    """
    👤 User endpoint with variable response time
    Simulates database calls with realistic latency
    """
    # Simulate realistic processing time
    await asyncio.sleep(random.uniform(0.1, 0.5))  # nosec #noqa: S311

    # Simulate not found scenarios
    if user_id == 404:
        raise HTTPException(status_code=404, detail="User not found")

    logger.info(
        "User login attempt",
        user="aandrieu",
        success=True,
        ip_address="192.168.1.1",
    )

    user = await db.get(User, user_id)
    return user.dict(exclude_unset=True)  # Return only non-default values to reduce serialization time

    # return {
    #     "user_id": user_id,
    #     "name": f"User {user_id}",
    #     "active": True,
    #     "created_at": "2024-01-01T00:00:00Z",
    # }


@router.post("/users/register")
async def register_user():
    logger.info("user_action", action="register")
    # Your registration logic
    USER_REGISTRATIONS.inc()
    return {"status": "registered"}


# Query a user and their associated orders in one go, avoiding the N+1 problem of "query 10 users + query 10 roles"
# async def get_user_with_roles(user_id: int, db: AsyncSession = Depends(get_db)):
#     return await db.execute(
#         select(User).options(select_related(User.role)).where(User.id == user_id)
#     ).scalar_one_or_none()
