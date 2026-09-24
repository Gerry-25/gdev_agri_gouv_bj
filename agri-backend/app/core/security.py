import hashlib
import hmac
import secrets
from datetime import timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.core.config import settings
from app.core.utils import utcnow

bearer_scheme = HTTPBearer(auto_error=False)

# Le superviseur dispose de tous les droits d'un agent, plus la validation des décisions sensibles
AGENT_ROLES = ("state_agent", "state_supervisor")


class CurrentUser(BaseModel):
    npi: str
    role: str

    @property
    def is_agent(self) -> bool:
        return self.role in AGENT_ROLES

    @property
    def is_supervisor(self) -> bool:
        return self.role == "state_supervisor"


def create_access_token(npi: str, role: str) -> str:
    now = utcnow()
    payload = {
        "sub": npi,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def hash_secret(value: str) -> str:
    """Empreinte HMAC d'un code ou jeton : seule l'empreinte est stockée en base."""
    return hmac.new(settings.JWT_SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()


def generate_otp() -> str:
    return f"{secrets.randbelow(10 ** settings.OTP_LENGTH):0{settings.OTP_LENGTH}d}"


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _decode(token: str) -> CurrentUser:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Jeton expiré.")
    except jwt.InvalidTokenError:
        raise _unauthorized("Jeton invalide.")
    return CurrentUser(npi=payload["sub"], role=payload.get("role", "farmer"))


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    if credentials is None:
        raise _unauthorized("Authentification requise.")
    return _decode(credentials.credentials)


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser | None:
    return _decode(credentials.credentials) if credentials else None


def require_roles(*roles: str):
    """Dépendance qui restreint une route à certains rôles."""

    allowed = set(roles) | ({"state_supervisor"} if "state_agent" in roles else set())

    async def checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès refusé pour ce rôle.")
        return user

    return checker
