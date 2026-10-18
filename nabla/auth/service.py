from fastapi import HTTPException, status
from keycloak.exceptions import KeycloakAuthenticationError
from keycloak import KeycloakOpenID

from nabla.config_settings import get_keycloak_openid, keycloak_configured
from nabla.auth.models import UserInfo


def _keycloak() -> KeycloakOpenID:
    """Return the Keycloak client, or answer 503 when Keycloak is not configured."""
    if not keycloak_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Keycloak authentication is not configured",
        )
    return get_keycloak_openid()


class AuthService:
    @staticmethod
    def authenticate_user(username: str, password: str) -> str:
        """
        Authenticate the user using Keycloak and return an access token.
        """
        try:
            token = _keycloak().token(username, password)
            return token["access_token"]
        except KeycloakAuthenticationError:
            raise HTTPException(  # noqa: B904
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

    @staticmethod
    def verify_token(token: str) -> UserInfo:
        """
        Verify the given token and return user information.
        """
        try:
            user_info = _keycloak().userinfo(token)
            print(user_info)
            if not user_info:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token",
                )
            return UserInfo(
                preferred_username=user_info["preferred_username"],
                email=user_info.get("email"),
                full_name=user_info.get("name"),
            )
        except KeycloakAuthenticationError:
            raise HTTPException(  # noqa: B904
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
            )
