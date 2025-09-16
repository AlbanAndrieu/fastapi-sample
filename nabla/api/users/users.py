import asyncio
import random
from typing import Annotated

import pybreaker
from fastapi import APIRouter, Depends, HTTPException, status
from fastmcp import FastMCP
from jwt import PyJWTError

# from fastapi_cache.decorator import cache
from pydantic import BaseModel
from sqlalchemy import Boolean, Column, Integer, String, select
from sqlalchemy.orm import declarative_base

from nabla.api.auth.token import TokenData, decode_jwt, oauth2_scheme
from nabla.db import get_db
from nabla.utils.logger import logger
from nabla.utils.prometheus import USER_REGISTRATIONS

router = APIRouter(prefix="/test")
mcp = FastMCP(name="UserServer")

Base = declarative_base()

circuit_breaker_user = pybreaker.CircuitBreaker(fail_max=2, reset_timeout=10)

class UserEvent(BaseModel):
    name: str
    email: str
    password: str
    # active: bool
    # role: str
    # permissions: list[str]
    # groups: list[str]mcp
    phone: str
    address: str
    city: str
    state: str
    zipcode: str
    country: str

    def __init__(self, name  = "Alban Andrieu", email = "alban.andrieu@free.fr", password = "XXX", phone = "0695435353", address = "11 terrasse de l'université", city = "Paris", state = "FR", zipcode = "92000", country = "France") -> None:  # noqa: S107
        super().__init__(name=name, email=email, password=password, phone=phone, address=address, city=city, state=state, zipcode=zipcode, country=country)

        # self.active = True
        # self.role = "admin"
        # self.permissions = ["read", "write"]
        # self.groups = ["admin"]
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
    password = Column(String, nullable=True)
    active = Column(Boolean, nullable=True)
    role = Column(String, nullable=True)
    permissions = Column(String, nullable=True)
    groups = Column(String, nullable=True)


    def __str__(self):
        return f"User ID : {self.id}\tName : {self.name}\tEmail : {self.email}\tPassword : {self.password}\tActive : {self.active}\tRole : {self.role}\tPermissions : {self.permissions}\tGroups : {self.groups}"


@mcp.tool(
    name="get_user_details",
    exclude_args=["user_id"]
)
def get_user_details(user_id: str = None) -> UserEvent:
# def get_user_details(user_id: str = None) -> dict[str, str]:
    # user_id will be injected by the server, not provided by the LLM
    if user_id is None:
        logger.info("get_user_details", user_id=user_id)

    return get_me()

def get_me() -> UserEvent:
    user = UserEvent(
        name="Alban Andrieu",
        email="alban.andrieu@free.fr",
        phone="0695435353",
        address="11 terrasse de l'université",
        city="Paris",
        state="FR",
        zipcode="92000",
        country="France",
    )

    return user

# This endpoint will not be registered as a tool, since it was added after the MCP instance was created
# Dynamic resource template
@mcp.resource("users://whoami/profile")
@router.get("/whoami/", operation_id="whoami", response_model=dict[str, str])
async def whoami():
    return get_me()


#def me()-> dict[str, str]:
# @router.get("/users/current", response_model=UserEvent)
@router.get("/users/current")
async def current_user():
    # return {"status": "registered"}
    # return json.loads(get_user_details(None))
    # return json.dumps(get_user_details(None))

    # user = get_user_details(None)
    # return UserEvent(**user)
    return get_me()
    # return {
    #     "name": "Alban Andrieu",
    #     "email": "alban.andrieu@free.fr",
    #     "phone": "0695435353",
    #     "address": "11 terrasse de l'université",
    #     "city": "Paris",
    #     "state": "FR",
    #     "zip": "92000",
    #     "country": "France",
    #     "job": "DevSecOps",
    #     "company": "JusMundi",
    #     "linkedin": "https://www.linkedin.com/in/nabla/",
    #     "github": "https://github.com/albanandrieu",
    #     "twitter": "https://twitter.com/nabla",
    #     "facebook": "https://www.facebook.com/aandrieu",
    #     "instagram": "https://www.instagram.com/aandrieu/",
    # }

async def get_user_by_email(email: str):
    return (await get_db().scalars(select(User).where(User.email == email))).first()


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_jwt(token)
        email = payload.get("sub")
        if email is None:
            raise credentials_exception
        permissions = payload.get("permissions")
        if permissions is None:
            raise credentials_exception
        token_data = TokenData(email=email, permissions=permissions)
    except PyJWTError:
        raise credentials_exception
    user = await get_user_by_email(token_data.email)
    if user is None:
        raise credentials_exception
    return user


currentUserDep = Annotated[User, Depends(get_current_user)]


async def validate_is_authenticated(
    current_user: currentUserDep,
) -> User:
    """
    This just returns as the CurrentUserDep dependency already throws if there is an issue with the auth token.
    """
    return current_user


# Dynamic resource template
@mcp.resource("users://{user_id}/profile")
@router.get("/users/{user_id}", response_model=UserEvent, operation_id="get_user_info",  dependencies=[Depends(validate_is_authenticated)])
# @circuit_breaker_user
# @cache(expire=300)  # Cache for 5 minutes to avoid repeated execution of complex SQL
# async def get_user(user_id: int, db=Depends(get_db)):
async def get_user(user_id: int):
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
        "User retrieve attempt",
        user="aandrieu",
        success=True,
        ip_address="192.168.1.1",
    )

    # user = await db.get(User, user_id)
    # return user.dict(exclude_unset=True)  # Return only non-default values to reduce serialization time
    user = (await get_db().scalars(select(User).where(User.id == user_id))).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

    # return {
    #     "name": f"User {user_id}",
    #     "email": "alban.andrieu@free.fr",
    #     "password": "XXX",
    #     # "active": True,
    #     # "role": "admin",
    #     # "permissions": ["read", "write"],
    #     # "groups": ["admin"],
    #     # "phone": "0695435353",
    #     # "address": "11 terrasse de l'université",
    #     # "city": "Paris",
    #     # "state": "FR",
    #     # "zip": "92000",
    #     # "country": "France",
    #     # "created_at": "2024-01-01T00:00:00Z",
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
