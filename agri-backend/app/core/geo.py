"""Outils géographiques : validation des contours GPS, surfaces, chevauchements, GeoJSON.

Les calculs de surface se font en UTM zone 31N (EPSG:32631), qui couvre tout le Bénin.
"""
import json

from pyproj import Transformer
from shapely.geometry import Point, Polygon, mapping, shape
from shapely.geometry.polygon import orient
from shapely.ops import transform
from shapely.validation import explain_validity

# lon_min, lat_min, lon_max, lat_max (avec une petite marge)
BENIN_BBOX = (0.70, 6.00, 3.90, 12.50)
COORD_DECIMALS = 7  # ~1 cm

_to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32631", always_xy=True).transform


class GeometryError(ValueError):
    pass


def in_benin(lon: float, lat: float) -> bool:
    lon_min, lat_min, lon_max, lat_max = BENIN_BBOX
    return lon_min <= lon <= lon_max and lat_min <= lat <= lat_max


def build_polygon(points: list[tuple[float, float]]) -> Polygon:
    """Construit un polygone valide à partir de points (lon, lat) relevés au GPS."""
    cleaned: list[tuple[float, float]] = []
    for lon, lat in points:
        p = (round(lon, COORD_DECIMALS), round(lat, COORD_DECIMALS))
        if not cleaned or p != cleaned[-1]:
            cleaned.append(p)
    if len(cleaned) > 1 and cleaned[0] == cleaned[-1]:
        cleaned.pop()  # le polygone est refermé automatiquement
    if len(set(cleaned)) < 3:
        raise GeometryError("Au moins 3 points GPS distincts sont nécessaires pour tracer une parcelle.")
    for lon, lat in cleaned:
        if not in_benin(lon, lat):
            raise GeometryError(f"Le point (lat {lat}, lon {lon}) est hors du territoire béninois.")
    poly = Polygon(cleaned)
    if not poly.is_valid:
        raise GeometryError(
            "Le contour est invalide : les côtés se croisent. Relevez les points dans l'ordre, "
            f"en faisant le tour de la parcelle ({explain_validity(poly)})."
        )
    # Sens antihoraire exigé par la norme GeoJSON (RFC 7946)
    return orient(poly, sign=1.0)


def to_utm(geom):
    return transform(_to_utm, geom)


def area_m2(poly: Polygon) -> float:
    return to_utm(poly).area


def perimeter_m(poly: Polygon) -> float:
    return to_utm(poly).length


def overlap_area_m2(a, b) -> float:
    return to_utm(a).intersection(to_utm(b)).area


def centroid_point(poly: Polygon) -> Point:
    c = poly.centroid
    return Point(round(c.x, COORD_DECIMALS), round(c.y, COORD_DECIMALS))


def to_geojson(geom) -> dict:
    # json aller-retour : convertit les tuples de shapely en listes
    return json.loads(json.dumps(mapping(geom)))


def from_geojson(data: dict):
    return shape(data)


def bbox_polygon(bbox: str) -> dict:
    """'lon_min,lat_min,lon_max,lat_max' → polygone GeoJSON (pour filtrer la vue d'une carte)."""
    try:
        lon_min, lat_min, lon_max, lat_max = (float(x) for x in bbox.split(","))
    except ValueError:
        raise GeometryError("bbox attendu : lon_min,lat_min,lon_max,lat_max")
    if lon_min >= lon_max or lat_min >= lat_max:
        raise GeometryError("bbox incohérent : les minimums doivent être inférieurs aux maximums.")
    return {
        "type": "Polygon",
        "coordinates": [[[lon_min, lat_min], [lon_max, lat_min], [lon_max, lat_max], [lon_min, lat_max], [lon_min, lat_min]]],
    }


def feature(geometry: dict, properties: dict) -> dict:
    return {"type": "Feature", "geometry": geometry, "properties": properties}


def feature_collection(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}
