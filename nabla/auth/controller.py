from fastapi import Depends, Form, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from nabla.auth.models import TokenResponse, UserInfo
from nabla.auth.service import AuthService

# Initialize HTTPBearer security dependency
bearer_scheme = HTTPBearer()


class AuthController:
    """
    Controller for handling authentication logic.
    """

    @staticmethod
    def read_root():
        """
        Root endpoint providing basic information and documentation link.

        Returns:
            dict: A welcome message and link to the documentation.
        """
        return {
            "message": (
                "Welcome to the Generic authentication system. "
                "Use the login endpoint to authenticate with the generic system and protected to access the protected resource."
                "Use the auth/login endpoint to authenticate with Keycloak and auth/protected to access the protected resource."
            ),
            "documentation": "/docs",
        }

    @staticmethod
    def login(username: str = Form(...), password: str = Form(...)) -> TokenResponse:
        """
        Authenticate user and return access token.

        Args:
            username (str): The username of the user attempting to log in.
            password (str): The password of the user.

        Raises:
            HTTPException: If the authentication fails (wrong credentials).

        Returns:
            TokenResponse: Contains the access token upon successful authentication.
        """
        # Authenticate the user using the AuthService
        access_token = AuthService.authenticate_user(username, password)

        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        return TokenResponse(access_token=access_token)

    @staticmethod
    def protected_endpoint(
        credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),  # noqa: B008
    ) -> UserInfo:
        """
        Access a protected resource that requires valid token authentication.

        Args:
            credentials (HTTPAuthorizationCredentials): Bearer token provided via HTTP Authorization header.

        Raises:
            HTTPException: If the token is invalid or not provided.

        Returns:
            UserInfo: Information about the authenticated user.
        """
        # Extract the bearer token from the provided credentials
        token = credentials.credentials

        # Verify the token and get user information
        user_info = AuthService.verify_token(token)

        if not user_info:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return user_info
