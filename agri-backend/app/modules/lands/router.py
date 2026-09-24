from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.core.database import get_database
from app.core.security import CurrentUser, get_current_user, require_roles
from app.core.utils import serialize_doc, utcnow
from app.modules.lands.schemas import LandCreateSchema, LandOut

router = APIRouter(prefix="/lands", tags=["Gestion Foncière"])


@router.post("/", status_code=status.HTTP_201_CREATED)
async def register_land(
    payload: LandCreateSchema,
    db=Depends(get_database),
    user: CurrentUser = Depends(require_roles("farmer")),
):
    doc = {
        **payload.model_dump(),
        "npi_owner": user.npi,  # le propriétaire est l'utilisateur authentifié
        "dispute_flag": False,
        "created_at": utcnow(),
    }
    try:
        result = await db["lands"].insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cette référence cadastrale est déjà enregistrée.")
    return {"id": str(result.inserted_id), "status": "registered"}


async def _lands_for(db, npi: str) -> list[dict]:
    cursor = db["lands"].find({"npi_owner": npi}).sort("created_at", -1)
    return [serialize_doc(item) async for item in cursor]


@router.get("/me", response_model=list[LandOut])
async def get_my_lands(db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    return await _lands_for(db, user.npi)


@router.get("/owner/{npi}", response_model=list[LandOut])
async def get_lands_by_owner(npi: str, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    # Un exploitant ne voit que ses parcelles ; un agent de l'État voit tout
    if user.npi != npi and user.role != "state_agent":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès refusé.")
    return await _lands_for(db, npi)
