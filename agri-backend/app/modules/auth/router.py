from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.core.config import settings
from app.core.database import get_database
from app.core.security import CurrentUser, create_access_token, get_current_user
from app.core.utils import utcnow
from app.modules.auth.schemas import CitizenAuthSchema, TokenResponse, UserProfile

router = APIRouter(prefix="/auth", tags=["Authentification NPI"])


@router.post("/login-npi", response_model=TokenResponse)
async def login_with_npi(payload: CitizenAuthSchema, db=Depends(get_database)):
    users_coll = db["users"]
    user = await users_coll.find_one({"npi": payload.npi})

    if not user:
        new_user = {**payload.model_dump(), "created_at": utcnow()}
        try:
            await users_coll.insert_one(new_user)
            user = new_user
        except DuplicateKeyError:
            # Inscription simultanée avec le même NPI
            user = await users_coll.find_one({"npi": payload.npi})

    # Vérification minimale : le téléphone doit correspondre à celui enregistré
    if user["phone"] != payload.phone:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="NPI ou téléphone incorrect.")

    # Le rôle vient toujours de la base, jamais de la requête
    role = user["role"]
    return TokenResponse(
        access_token=create_access_token(user["npi"], role),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_npi=user["npi"],
        role=role,
    )


@router.get("/me", response_model=UserProfile)
async def read_me(current: CurrentUser = Depends(get_current_user), db=Depends(get_database)):
    user = await db["users"].find_one({"npi": current.npi})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")
    return UserProfile(**user)
