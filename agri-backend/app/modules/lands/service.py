"""Logique foncière : géométrie des parcelles, chevauchements et litiges."""
from statistics import mean

from bson import ObjectId
from fastapi import HTTPException, status

from app.core import geo
from app.core.config import settings
from app.core.security import CurrentUser
from app.core.utils import parse_object_id, utcnow
from app.modules.lands.schemas import OPEN_DISPUTE_STATUSES, LandBoundaryInput
from app.modules.notifications.service import notify


async def get_land_or_404(db, land_id: str) -> dict:
    land = await db["lands"].find_one({"_id": parse_object_id(land_id, "Parcelle")})
    if not land:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parcelle introuvable.")
    return land


def ensure_owner(land: dict, user: CurrentUser) -> None:
    if land["npi_owner"] != user.npi:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cette parcelle ne vous appartient pas.")


def ensure_owner_or_agent(land: dict, user: CurrentUser) -> None:
    if land["npi_owner"] != user.npi and not user.is_agent:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès refusé.")


def geometry_from_boundary(boundary: LandBoundaryInput):
    """Valide le contour et calcule surface, périmètre et centre."""
    try:
        poly = geo.build_polygon([(p.longitude, p.latitude) for p in boundary.points])
    except geo.GeometryError as e:
        raise HTTPException(status_code=422, detail=str(e))

    area = geo.area_m2(poly)
    if area < settings.LAND_MIN_AREA_M2:
        raise HTTPException(
            status_code=422,
            detail=f"Surface trop petite ({area:.0f} m²) : vérifiez que les points font bien le tour de la parcelle.",
        )
    if area > settings.LAND_MAX_AREA_HA * 10_000:
        raise HTTPException(
            status_code=422,
            detail=f"Surface supérieure à {settings.LAND_MAX_AREA_HA:.0f} ha : vérifiez les points GPS.",
        )

    accuracies = [p.accuracy_m for p in boundary.points if p.accuracy_m is not None]
    points_count = len(poly.exterior.coords) - 1
    info = {
        "boundary": geo.to_geojson(poly),
        "centroid": geo.to_geojson(geo.centroid_point(poly)),
        "surface_hectares": round(area / 10_000, 4),
        "perimeter_m": round(geo.perimeter_m(poly), 1),
        "points_count": points_count,
        "gps_accuracy_mean_m": round(mean(accuracies), 1) if accuracies else None,
        "capture_method": boundary.capture_method,
    }

    warnings = []
    if accuracies and mean(accuracies) > 10:
        warnings.append("Précision GPS moyenne supérieure à 10 m : la surface peut être imprécise. Refaites le relevé à découvert si possible.")
    if points_count < 6:
        warnings.append("Peu de points relevés : le contour est approximatif. Ajoutez un point à chaque changement de direction de la bordure.")
    return poly, info, warnings


async def candidate_lands(db, geojson: dict, exclude_id: ObjectId | None = None, collection: str = "lands") -> list[dict]:
    """Présélection par l'index 2dsphere des contours (parcelles ou terres de l'État) qui touchent le polygone."""
    query: dict = {"boundary": {"$geoIntersects": {"$geometry": geojson}}}
    if exclude_id is not None:
        query["_id"] = {"$ne": exclude_id}
    cursor = db[collection].find(query, {"boundary": 1, "npi_owner": 1, "department": 1, "commune": 1, "name": 1, "status": 1})
    return [d async for d in cursor]


async def find_overlaps(db, poly, exclude_id: ObjectId | None = None, collection: str = "lands") -> list[dict]:
    """Chevauchements réels au-delà de la tolérance (les bordures partagées sont ignorées)."""
    overlaps = []
    for land in await candidate_lands(db, geo.to_geojson(poly), exclude_id, collection):
        area = geo.overlap_area_m2(poly, geo.from_geojson(land["boundary"]))
        if area > settings.LAND_OVERLAP_TOLERANCE_M2:
            overlaps.append({"land": land, "overlap_m2": round(area, 1)})
    return overlaps


def reject_own_overlaps(overlaps: list[dict], user: CurrentUser) -> list[dict]:
    own = [o for o in overlaps if o["land"]["npi_owner"] == user.npi]
    if own:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Ce contour chevauche une de vos parcelles déjà enregistrées.",
                "land_ids": [str(o["land"]["_id"]) for o in own],
            },
        )
    return overlaps


async def refresh_dispute_flags(db, land_ids: list[str], domain_ids: list[str] | None = None) -> None:
    for lid in set(land_ids):
        n = await db["disputes"].count_documents({"land_ids": lid, "status": {"$in": OPEN_DISPUTE_STATUSES}})
        await db["lands"].update_one({"_id": ObjectId(lid)}, {"$set": {"dispute_flag": n > 0}})
    for did in set(domain_ids or []):
        n = await db["disputes"].count_documents({"domain_id": did, "status": {"$in": OPEN_DISPUTE_STATUSES}})
        await db["state_domains"].update_one({"_id": ObjectId(did)}, {"$set": {"dispute_flag": n > 0}})


async def open_domain_disputes(db, land: dict, domain_overlaps: list[dict]) -> list[dict]:
    """Une parcelle privée empiète sur une terre du domaine privé de l'État : litige avec l'État."""
    land_id, now, results = str(land["_id"]), utcnow(), []
    for o in domain_overlaps:
        domain = o["land"]
        domain_id = str(domain["_id"])
        existing = await db["disputes"].find_one({
            "type": "chevauchement_domaine_etat", "land_ids": land_id, "domain_id": domain_id,
            "status": {"$in": OPEN_DISPUTE_STATUSES},
        })
        if existing:
            dispute_id = str(existing["_id"])
        else:
            res = await db["disputes"].insert_one({
                "type": "chevauchement_domaine_etat", "status": "ouvert", "land_ids": [land_id], "domain_id": domain_id,
                "parties_npi": [land["npi_owner"]], "reported_by": "systeme",
                "reason": f"La parcelle empiète de {o['overlap_m2']} m² sur la terre de l'État « {domain.get('name', domain_id)} ».",
                "department": land["department"], "commune": land["commune"], "overlap_area_m2": o["overlap_m2"],
                "history": [{"status": "ouvert", "by": "systeme", "at": now}], "created_at": now, "updated_at": now,
            })
            dispute_id = str(res.inserted_id)
            await notify(db, [land["npi_owner"]], "dispute_opened", "Chevauchement avec une terre de l'État",
                         f"Votre parcelle à {land['commune']} empiète sur une terre du domaine de l'État. Un agent va examiner la situation.",
                         {"dispute_id": dispute_id, "land_id": land_id})
        results.append({"domain_id": domain_id, "overlap_m2": o["overlap_m2"], "dispute_id": dispute_id})
    await refresh_dispute_flags(db, [land_id], [r["domain_id"] for r in results])
    return results


async def open_overlap_disputes(db, land: dict, overlaps: list[dict]) -> list[dict]:
    """Ouvre automatiquement un litige de chevauchement par parcelle voisine concernée."""
    land_id = str(land["_id"])
    now = utcnow()
    results = []
    for o in overlaps:
        other = o["land"]
        other_id = str(other["_id"])
        existing = await db["disputes"].find_one({
            "type": "chevauchement",
            "land_ids": {"$all": [land_id, other_id]},
            "status": {"$in": OPEN_DISPUTE_STATUSES},
        })
        if existing:
            await db["disputes"].update_one(
                {"_id": existing["_id"]}, {"$set": {"overlap_area_m2": o["overlap_m2"], "updated_at": now}}
            )
            dispute_id = str(existing["_id"])
        else:
            res = await db["disputes"].insert_one({
                "type": "chevauchement",
                "status": "ouvert",
                "land_ids": [land_id, other_id],
                "parties_npi": [land["npi_owner"], other["npi_owner"]],
                "reported_by": "systeme",
                "reason": f"Chevauchement de {o['overlap_m2']} m² détecté automatiquement entre deux contours GPS.",
                "department": land["department"],
                "commune": land["commune"],
                "overlap_area_m2": o["overlap_m2"],
                "history": [{"status": "ouvert", "by": "systeme", "at": now}],
                "created_at": now,
                "updated_at": now,
            })
            dispute_id = str(res.inserted_id)
            await notify(
                db, [land["npi_owner"], other["npi_owner"]], "dispute_opened",
                "Chevauchement de parcelles",
                f"Deux parcelles se chevauchent sur {o['overlap_m2']:.0f} m² à {land['commune']}. Un agent va examiner la situation.",
                {"dispute_id": dispute_id, "land_ids": [land_id, other_id]},
            )
        results.append({"land_id": other_id, "overlap_m2": o["overlap_m2"], "dispute_id": dispute_id})

    await refresh_dispute_flags(db, [land_id] + [r["land_id"] for r in results])
    return results
