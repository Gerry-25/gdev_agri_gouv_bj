from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pymongo.errors import DuplicateKeyError

from app.core.config import settings
from app.core.database import get_database
from app.core.security import (
    CurrentUser,
    create_access_token,
    generate_otp,
    generate_refresh_token,
    get_current_user,
    hash_secret,
)
from app.core.sms import get_sms_sender, mask_phone
from app.core.utils import as_utc as _aware, utcnow
from app.modules.auth.schemas import (
    OtpRequest,
    OtpRequestResponse,
    OtpVerify,
    ProfileUpdate,
    RefreshRequest,
    TokenResponse,
    UserProfile,
)

router = APIRouter(prefix="/auth", tags=["Authentification NPI"])

_BAD_CREDENTIALS = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="NPI ou téléphone incorrect.")


async def _issue_tokens(db, user: dict) -> TokenResponse:
    refresh = generate_refresh_token()
    now = utcnow()
    await db["refresh_tokens"].insert_one({
        "npi": user["npi"],
        "token_hash": hash_secret(refresh),
        "created_at": now,
        "expires_at": now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    })
    return TokenResponse(
        # Le rôle est toujours lu en base : une promotion s'applique au prochain rafraîchissement
        access_token=create_access_token(user["npi"], user["role"]),
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        refresh_expires_in=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        user=UserProfile(**user),
    )


@router.post("/otp/request", response_model=OtpRequestResponse, summary="Étape 1 : recevoir un code de connexion")
async def request_otp(payload: OtpRequest, db=Depends(get_database)):
    user = await db["users"].find_one({"npi": payload.npi})
    if user and user["phone"] != payload.phone:
        raise _BAD_CREDENTIALS
    if not user and not payload.full_name:
        raise HTTPException(status_code=422, detail="Première connexion : indiquez votre nom complet.")

    now = utcnow()
    previous = await db["otp_codes"].find_one({"npi": payload.npi})
    sends = []
    if previous:
        elapsed = (now - _aware(previous["last_sent_at"])).total_seconds()
        if elapsed < settings.OTP_RESEND_SECONDS:
            wait = int(settings.OTP_RESEND_SECONDS - elapsed) + 1
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=f"Patientez {wait} s avant de demander un nouveau code.", headers={"Retry-After": str(wait)})
        sends = [s for s in previous.get("sends", []) if (now - _aware(s)).total_seconds() < 3600]
        if len(sends) >= settings.OTP_MAX_PER_HOUR:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Trop de codes demandés. Réessayez dans une heure.", headers={"Retry-After": "3600"})

    code = generate_otp()
    pending = None if user else {
        "npi": payload.npi, "phone": payload.phone, "full_name": payload.full_name,
        "role": payload.role, "preferred_language": payload.preferred_language,
    }
    await db["otp_codes"].update_one({"npi": payload.npi}, {"$set": {
        "code_hash": hash_secret(f"{payload.npi}:{code}"),
        "phone": payload.phone,
        "attempts": 0,
        "pending_user": pending,
        "last_sent_at": now,
        "sends": sends + [now],
        "expires_at": now + timedelta(seconds=settings.OTP_TTL_SECONDS),
    }}, upsert=True)

    sender = get_sms_sender()
    await sender.send(payload.phone, f"AgriSmart : votre code de connexion est {code}. Il expire dans {settings.OTP_TTL_SECONDS // 60} min.")
    return OtpRequestResponse(
        message=f"Code envoyé au {mask_phone(payload.phone)}.",
        is_new_user=user is None,
        expires_in=settings.OTP_TTL_SECONDS,
        resend_in=settings.OTP_RESEND_SECONDS,
        delivery=sender.name,
        simulated_code=code if sender.exposes_code else None,
    )


@router.post("/otp/verify", response_model=TokenResponse, summary="Étape 2 : valider le code et obtenir les jetons")
async def verify_otp(payload: OtpVerify, db=Depends(get_database)):
    otp = await db["otp_codes"].find_one({"npi": payload.npi})
    if not otp or _aware(otp["expires_at"]) < utcnow():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Code expiré ou inexistant : demandez un nouveau code.")
    if otp["attempts"] >= settings.OTP_MAX_ATTEMPTS:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Trop d'essais : demandez un nouveau code.")

    if hash_secret(f"{payload.npi}:{payload.code}") != otp["code_hash"]:
        await db["otp_codes"].update_one({"_id": otp["_id"]}, {"$inc": {"attempts": 1}})
        left = settings.OTP_MAX_ATTEMPTS - otp["attempts"] - 1
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Code incorrect. Il vous reste {left} essai(s).")

    await db["otp_codes"].delete_one({"_id": otp["_id"]})
    user = await db["users"].find_one({"npi": payload.npi})
    if not user:
        if not otp.get("pending_user"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inscription introuvable : recommencez.")
        user = {**otp["pending_user"], "created_at": utcnow()}
        try:
            await db["users"].insert_one(user)
        except DuplicateKeyError:
            user = await db["users"].find_one({"npi": payload.npi})
    elif user["phone"] != otp["phone"]:
        raise _BAD_CREDENTIALS
    return await _issue_tokens(db, user)


@router.post("/refresh", response_model=TokenResponse, summary="Renouveler les jetons (rotation)")
async def refresh_tokens(payload: RefreshRequest, db=Depends(get_database)):
    record = await db["refresh_tokens"].find_one_and_delete({"token_hash": hash_secret(payload.refresh_token)})
    if not record or _aware(record["expires_at"]) < utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expirée : reconnectez-vous.")
    user = await db["users"].find_one({"npi": record["npi"]})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utilisateur introuvable.")
    return await _issue_tokens(db, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: RefreshRequest, db=Depends(get_database)):
    await db["refresh_tokens"].delete_one({"token_hash": hash_secret(payload.refresh_token)})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT, summary="Déconnecter tous mes appareils")
async def logout_all(db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    await db["refresh_tokens"].delete_many({"npi": user.npi})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserProfile)
async def read_me(current: CurrentUser = Depends(get_current_user), db=Depends(get_database)):
    user = await db["users"].find_one({"npi": current.npi})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")
    return UserProfile(**user)


@router.patch("/me", response_model=UserProfile)
async def update_me(payload: ProfileUpdate, current: CurrentUser = Depends(get_current_user), db=Depends(get_database)):
    changes = payload.model_dump(mode="json", exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Aucune modification fournie.")
    await db["users"].update_one({"npi": current.npi}, {"$set": {**changes, "updated_at": utcnow()}})
    return await read_me(current, db)
