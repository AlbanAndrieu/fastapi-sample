import uuid

from fastapi import Depends
from fastapi_users import schemas
from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from pydantic import BaseModel
from sqladmin import ModelView
from sqlalchemy import Column, String

# from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, declarative_base

from nabla.api.db.database import get_session
from nabla.utils.email import conf

Base = declarative_base()

class UserEvent(BaseModel):
    # model_config = ConfigDict(
    #     str_max_length=120,      # hard caps avoid pathological inputs
    #     extra="ignore",          # drop unknown fields instead of raising
    #     revalidate_instances="never",  # don't re-check already-validated data
    #     ser_json_inf_nan=False   # stricter but faster JSON
    # )

    name: str
    email: str
    password: str
    phone: str
    address: str
    city: str
    state: str
    zipcode: str
    country: str

    def __init__(self, name  = "Alban Andrieu", email = conf.MAIL_FROM, password = "XXX", phone = "0695435353", address = "11 terrasse de l'université", city = "Paris", state = "FR", zipcode = "92000", country = "France") -> None:  # noqa: S107
        super().__init__(name=name, email=email, password=password, phone=phone, address=address, city=city, state=state, zipcode=zipcode, country=country)


class UserRead(schemas.BaseUser[uuid.UUID]):
    pass


class UserCreate(schemas.BaseUserCreate):
    pass


class UserUpdate(schemas.BaseUserUpdate):
    pass

class User(SQLAlchemyBaseUserTableUUID, Base):
    # __tablename__ = "users"

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
async def get_user_db(session: Session = Depends(get_session)):
    yield SQLAlchemyUserDatabase(session, User)

class UserAdmin(ModelView, model=User):
    column_list = [User.id, User.email, User.name]
