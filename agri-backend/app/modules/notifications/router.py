from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.core.database import get_database
from app.core.security import CurrentUser, get_current_user
from app.core.utils import parse_object_id, serialize_doc

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class NotificationOut(BaseModel):
    id: str
    type: str
    title: str
    message: str
    pictogram: str
    data: dict
    read: bool
    created_at: datetime


@router.get("/me", response_model=list[NotificationOut])
async def my_notifications(
    db=Depends(get_database),
    user: CurrentUser = Depends(get_current_user),
    unread_only: bool = False,
    skip: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
):
    filters: dict = {"npi": user.npi}
    if unread_only:
        filters["read"] = False
    cursor = db["notifications"].find(filters).sort("created_at", -1).skip(skip).limit(limit)
    return [serialize_doc(d) async for d in cursor]


@router.get("/me/unread-count")
async def unread_count(db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    return {"unread": await db["notifications"].count_documents({"npi": user.npi, "read": False})}


@router.post("/me/read-all")
async def mark_all_read(db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    res = await db["notifications"].update_many({"npi": user.npi, "read": False}, {"$set": {"read": True}})
    return {"updated": res.modified_count}


@router.patch("/{notification_id}/read", response_model=NotificationOut)
async def mark_read(notification_id: str, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    oid = parse_object_id(notification_id, "Notification")
    res = await db["notifications"].update_one({"_id": oid, "npi": user.npi}, {"$set": {"read": True}})
    if not res.matched_count:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification introuvable.")
    return serialize_doc(await db["notifications"].find_one({"_id": oid}))
