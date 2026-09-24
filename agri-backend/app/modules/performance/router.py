from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.core.database import get_database
from app.core.security import CurrentUser, get_current_user, require_roles
from app.modules.performance.service import compute_score, compute_scores

router = APIRouter(tags=["Performance des exploitants"])


@router.get("/performance/me", summary="Mon score de performance et son explication")
async def my_performance(db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    return await compute_score(db, user.npi)


@router.get("/state/farmers/performance", summary="Classement des exploitants (agents)")
async def farmers_ranking(
    db=Depends(get_database),
    _: CurrentUser = Depends(require_roles("state_agent")),
    department: Optional[str] = Query(None, description="Exploitants ayant au moins une parcelle dans ce département"),
    crop: Optional[str] = Query(None, description="Exploitants ayant récolté cette culture"),
    min_score: float = Query(0, ge=0, le=100),
    eligible_only: bool = False,
    limit: int = Query(50, ge=1, le=500),
):
    rows = list((await compute_scores(db)).values())
    if department:
        rows = [r for r in rows if department in r["stats"]["departments"]]
    if crop:
        rows = [r for r in rows if crop.lower() in (c.lower() for c in r["stats"]["crops"])]
    rows = [r for r in rows if r["score"] >= min_score and (r["eligible"] or not eligible_only)]
    rows.sort(key=lambda r: (-r["score"], r["npi"]))
    for rank, r in enumerate(rows, 1):
        r["rank"] = rank
    return rows[:limit]


@router.get("/state/farmers/{npi}/performance", summary="Score détaillé d'un exploitant (agents)")
async def farmer_performance(npi: str, db=Depends(get_database), _: CurrentUser = Depends(require_roles("state_agent"))):
    return await compute_score(db, npi)
