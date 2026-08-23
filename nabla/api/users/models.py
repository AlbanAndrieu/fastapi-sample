import os
import uuid
from typing import Annotated

from fastapi import Depends
from fastapi_users import schemas
from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from pydantic import BaseModel, Field
from sqladmin import ModelView
from sqlalchemy import Column, String

# from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, declarative_base

from nabla.api.db.database import engine, get_session

Base = declarative_base()

_DEFAULT_USER_IN_EMAIL = os.environ.get("MAIL_FROM", "alban.andrieu@gmail.com")


async def init_db():
    # SQLModel.metadata.create_all(engine)
    Base.metadata.create_all(engine)


class PublicUserProfile(BaseModel):
    """Public identity fields that can be returned without exposing credentials."""

    user_id: str = Field(
        default="albandrieu",
        min_length=1,
        max_length=128,
        description="Application/database user id (handle)",
    )
    name: str = Field(min_length=1)
    email: str
    phone: str
    address: str
    city: str
    state: str
    zipcode: str
    country: str


class UserIn(PublicUserProfile):
    # model_config = ConfigDict(
    #     str_max_length=120,      # hard caps avoid pathological inputs
    #     extra="ignore",          # drop unknown fields instead of raising
    #     revalidate_instances="never",  # don't re-check already-validated data
    #     ser_json_inf_nan=False   # stricter but faster JSON
    # )

    password: str

    def __init__(
        self,
        user_id: str = "albandrieu",
        name="Alban Andrieu",
        email: str = _DEFAULT_USER_IN_EMAIL,
        password="XXX",  # noqa: S107 noqa:B107 # nosec B107
        phone="",
        address="Paris, France",
        city="Paris",
        state="FR",
        zipcode="",
        country="France",
    ) -> None:
        super().__init__(
            user_id=user_id,
            name=name,
            email=email,
            password=password,
            phone=phone,
            address=address,
            city=city,
            state=state,
            zipcode=zipcode,
            country=country,
        )


class UserOut(PublicUserProfile):
    """Authenticated user response without the input password field."""

    id: int


class UserRead(schemas.BaseUser[uuid.UUID]):
    pass


class UserCreate(schemas.BaseUserCreate):
    pass


class UserUpdate(schemas.BaseUserUpdate):
    pass


class User(SQLAlchemyBaseUserTableUUID, Base):
    # __tablename__ = "user"

    # id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    # email = Column(String, nullable=False)
    # password = Column(String, nullable=True)
    # active = Column(Boolean, nullable=True)
    # role = Column(String, nullable=True)
    # permissions = Column(String, nullable=True)
    # groups = Column(String, nullable=True)

    # def __str__(self):
    #     return f"User ID : {self.id}\tName : {self.name}\tEmail : {self.email}\tPassword : {self.password}\tActive : {self.active}\tRole : {self.role}\tPermissions : {self.permissions}\tGroups : {self.groups}"
    pass


# async def get_user_db(session: AsyncSession = Depends(get_async_session)):
#     yield SQLAlchemyUserDatabase(session, User)
async def get_user_db(session: Annotated[Session, Depends(get_session)]):
    yield SQLAlchemyUserDatabase(session, User)


class UserAdmin(ModelView, model=User):
    column_list = [User.id, User.name]
    # column_list = [User.id, User.email, User.name]
