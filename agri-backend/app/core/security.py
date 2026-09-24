from datetime import timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.core.config import settings
from app.core.utils import utcnow

bearer_scheme = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    npi: str
    role: str


def create_access_token(npi: str, role: str) -> str:
    now = utcnow()
    payload = {
        "sub": npi,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    if credentials is None:
        raise _unauthorized("Authentification requise.")
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Jeton expiré.")
    except jwt.InvalidTokenError:
        raise _unauthorized("Jeton invalide.")
    return CurrentUser(npi=payload["sub"], role=payload.get("role", "farmer"))


def require_roles(*roles: str):
    """Dépendance qui restreint une route à certains rôles."""

    async def checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès refusé pour ce rôle.")
        return user

    return checker
