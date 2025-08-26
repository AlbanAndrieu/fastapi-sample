from fastapi import APIRouter, Depends, Form
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from nabla.auth.controller import AuthController
from nabla.auth.models import TokenResponse, UserInfo
from nabla.utils.logger import logger

router = APIRouter()


# Initialize the HTTPBearer scheme for authentication
bearer_scheme = HTTPBearer()


# Define the login endpoint
@router.post("/login", response_model=TokenResponse)
async def login(username: str = Form(...), password: str = Form(...)):
    """
    Login endpoint to authenticate the user and return an access token.

    Args:
        username (str): The username of the user attempting to log in.
        password (str): The password of the user.

    Returns:
        TokenResponse: Contains the access token upon successful authentication.
    """
    logger.info("user_action", action="login")
    return AuthController.login(username, password)


# Define the protected endpoint
@router.get("/protected", response_model=UserInfo)
async def protected_endpoint(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),  # noqa: B008
):
    """
    Protected endpoint that requires a valid token for access.

    Args:
        credentials (HTTPAuthorizationCredentials): Bearer token provided via HTTP Authorization header.

    Returns:
        UserInfo: Information about the authenticated user.
    """
    return AuthController.protected_endpoint(credentials)
