import asyncio

import pytest
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.testclient import TestClient
from passlib.context import CryptContext

from nabla.api.auth.token import create_access_token
from nabla.api.db.database import database
from server import app
from tests.unit.conftest import requires_env


@pytest.fixture(scope="module")
def test_app():
    client = TestClient(app)
    yield client  # testing happens here

@pytest.fixture(scope="session")
def event_loop(request):
    loop = asyncio.get_event_loop()
    yield loop
    # loop.close()


@requires_env("DEV", "UAT")
def test_login(test_app):
    response = test_app.post(
        "/auth/login",
        data={
            "username": "testuser1",
            "password": "qwerty@123"
        }
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


@requires_env("DEV", "UAT")
def test_login_b(test_app):
    response = test_app.post(
        "/auth/login",
        data={
            "username": "johndoe",
            "password": "qwerty@123"
        }
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


### LOGIN ###

@pytest.mark.skip(reason="Skipping this test for now")
@app.post("/login", tags=["auth"])
async def login(request: OAuth2PasswordRequestForm = Depends()):
    user = await database["users"].find_one({"username": request.username})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid username or password"
        )

    if not CryptContext().verify(user["password"], request.password):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid username or password"
        )
    access_token = create_access_token(data={"sub": user["username"]})
    return {"access_token": access_token, "token_type": "bearer"}
