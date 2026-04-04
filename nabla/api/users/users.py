import asyncio
import os
import random
import uuid
from typing import Annotated, Optional

import pybreaker
from fastapi_cache.decorator import cache
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    CookieTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase
from fastmcp import FastMCP
from fastmcp.dependencies import Depends as McpDepends
from jwt import PyJWTError

# from fastapi_cache.decorator import cache
from sqlalchemy import select
from sqlmodel import Session

from fastapi import APIRouter, Depends, HTTPException, Request, status
from nabla.api.auth.token import (
    ACCESS_TOKEN_SECRET_KEY,
    TokenData,
    create_access_token,
    decode_jwt,
    get_password_hash,
    oauth2_scheme,
    verify_password,
)
from nabla.api.db.database import get_db, get_session
from nabla.api.users.models import User, UserIn, UserOut, get_user_db
from nabla.utils.logger import logger
from nabla.utils.prometheus import USER_REGISTRATIONS

# OAuth 2.0 access token `token_type` (RFC 6749 §5.1); public keyword, not a credential.
OAUTH2_ACCESS_TOKEN_TYPE = "bearer"  # noqa: S105  # nosec B105

router = APIRouter(prefix="/test")
mcp = FastMCP(name="UserServer")

circuit_breaker_user = pybreaker.CircuitBreaker(fail_max=2, reset_timeout=10)

bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")
cookie_transport = CookieTransport(cookie_max_age=3600)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = ACCESS_TOKEN_SECRET_KEY
    verification_token_secret = ACCESS_TOKEN_SECRET_KEY

    async def on_after_register(self, user: User, request: Optional[Request] = None):
        print(f"User {user.id} has registered.")

    async def on_after_forgot_password(
        self,
        user: User,
        token: str,
        request: Optional[Request] = None,
    ):
        print(f"User {user.id} has forgot their password. Reset token: {token}")

    async def on_after_request_verify(
        self,
        user: User,
        token: str,
        request: Optional[Request] = None,
    ):
        print(f"Verification requested for user {user.id}. Verification token: {token}")


async def get_user_manager(user_db: Annotated[SQLAlchemyUserDatabase, Depends(get_user_db)]):
    yield UserManager(user_db)


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=ACCESS_TOKEN_SECRET_KEY, lifetime_seconds=3600)


jwt_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

cookie_backend = AuthenticationBackend(
    name="jwt",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)

# Just define your user model, plug it into FastAPI Users
# fastapi_users = FastAPIUsers(get_user_db, [jwt_backend], User, UserCreate, UserUpdate)
fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [jwt_backend])


async def get_enabled_backends(request: Request):
    """Return the enabled dependencies following custom logic."""
    if request.url.path == "/protected-route-only-jwt":
        return [jwt_backend]
    else:
        return [cookie_backend, jwt_backend]


# current_active_user = Annotated[User, Depends(get_current_user)]
current_active_user = fastapi_users.current_user(active=True, get_enabled_backends=get_enabled_backends)


def _get_user_details_user_id() -> str | None:
    """Injected server-side for MCP; omitted from the tool input schema."""
    return None


@mcp.tool(name="get_user_details")
def get_user_details(user_id: str | None = McpDepends(_get_user_details_user_id)) -> UserIn:
    # def get_user_details(user_id: str = None) -> dict[str, str]:
    # user_id will be injected by the server, not provided by the LLM
    if user_id is None:
        logger.info("get_user_details", user_id=user_id)

    user = {"id": 1, **get_me()}
    return user


def get_me() -> UserIn:
    user = UserIn(
        name="Alban Andrieu",
        email=os.environ.get("MAIL_FROM", "alban.andrieu@gmail.com"),
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
@router.get("/whoami/", operation_id="whoami", response_model=UserIn)
async def whoami():
    return get_me()


# def me()-> dict[str, str]:
# @router.get("/users/current", response_model=UserIn)
@cache(expire=300)
@router.get("/users/current", response_model=UserOut)
async def current_user():
    # return {"status": "registered"}
    # return json.loads(get_user_details(None))
    # return json.dumps(get_user_details(None))

    # user = get_user_details(None)
    # return UserIn(**user)
    return get_me()


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
        raise credentials_exception from None
    user = await get_user_by_email(token_data.email)
    if user is None:
        raise credentials_exception
    return user


@router.get("/protected-route")
def protected_route(user: Annotated[User, Depends(current_active_user)]):
    return f"Hello, {user.email}. You are authenticated with a cookie or a JWT."


@router.get("/protected-route-only-jwt")
def protected_route_only_jwt(user: Annotated[User, Depends(current_active_user)]):
    return f"Hello, {user.email}. You are authenticated with a JWT."


async def validate_is_authenticated(
    current_user: current_active_user,
) -> User:
    """
    This just returns as the CurrentUserDep dependency already throws if there is an issue with the auth token.
    """
    return current_user


# Dynamic resource template
@mcp.resource("users://{user_id}/profile")
@router.get("/users/{user_id}", response_model=UserOut, operation_id="get_user_info", dependencies=[Depends(validate_is_authenticated)])
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


@router.post("/users/register", response_model=UserOut, status_code=201)
async def register(user: UserIn, session: Annotated[Session, Depends(get_session)]):
    result = await session.execute(select(User).where(User.name == user.name))
    if result.scalar():
        raise HTTPException(status_code=400, detail="User already exists")
    new_user = User(name=user.name, hashed_password=get_password_hash(user.password))
    session.add(new_user)
    await session.commit()

    logger.info("user_action", action="register")
    # Your registration logic
    USER_REGISTRATIONS.inc()
    user = {"id": 1, **user.model_dump()}
    return {"status": "User created", "user": user}


@router.post("/login")
async def login(user: UserIn, session: Annotated[Session, Depends(get_session)]):
    result = await session.execute(select(User).where(User.name == user.name))
    db_user = result.scalar()
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access_token = create_access_token(data={"sub": db_user.name})
    return {"access_token": access_token, "token_type": OAUTH2_ACCESS_TOKEN_TYPE}


# Query a user and their associated orders in one go, avoiding the N+1 problem of "query 10 users + query 10 roles"
# async def get_user_with_roles(user_id: int, db: AsyncSession = Depends(get_db)):
#     return await db.execute(
#         select(User).options(select_related(User.role)).where(User.id == user_id)
#     ).scalar_one_or_none()
