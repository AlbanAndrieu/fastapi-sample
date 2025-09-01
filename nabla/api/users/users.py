import asyncio
import random

from fastapi import APIRouter, HTTPException

from nabla.utils.logger import logger
from nabla.utils.prometheus import USER_REGISTRATIONS

router = APIRouter(prefix="/test")

@router.get("/users/{user_id}", operation_id="get_user_info")
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
        "User login attempt",
        user="aandrieu",
        success=True,
        ip_address="192.168.1.1",
    )

    return {
        "user_id": user_id,
        "name": f"User {user_id}",
        "active": True,
        "created_at": "2024-01-01T00:00:00Z",
    }


@router.post("/users/register")
async def register_user():
    logger.info("user_action", action="register")
    # Your registration logic
    USER_REGISTRATIONS.inc()
    return {"status": "registered"}
