# AgriSmart Benin API

## Démarrage

```bash
./init_env.sh              # génère .env avec des secrets aléatoires
# (optionnel) ajoutez GEMINI_API_KEY dans .env : diagnostic IA réel + lecture audio
docker compose up -d --build
```

Documentation interactive : http://localhost:8000/docs

## Authentification

`POST /api/v1/auth/login-npi` renvoie un jeton JWT, à envoyer dans `Authorization: Bearer <jeton>`.
Les téléphones sont normalisés en `+22901XXXXXXXX` (les anciens numéros à 8 chiffres reçoivent le préfixe 01).

Le rôle `state_agent` ne peut pas être choisi à l'inscription :

```bash
docker compose exec api python -m app.scripts.promote_user <NPI> state_agent
```

## Parcelles par contour GPS (pour le frontend)

L'exploitant fait le tour de son champ ; le frontend envoie les points **dans l'ordre** :

```json
POST /api/v1/lands/
{
  "department": "Ouémé", "commune": "Dangbo", "locality": "Houédomè",
  "crop_type": "Manioc", "estimated_yield_kg": 8000,
  "boundary": {
    "capture_method": "gps_walk",
    "points": [
      {"latitude": 6.5800, "longitude": 2.5500, "accuracy_m": 4},
      {"latitude": 6.5800, "longitude": 2.5509, "accuracy_m": 5},
      {"latitude": 6.5809, "longitude": 2.5509, "accuracy_m": 4},
      {"latitude": 6.5809, "longitude": 2.5500, "accuracy_m": 6}
    ]
  }
}
```

Le serveur :
- referme le polygone et vérifie que les côtés ne se croisent pas et que tous les points sont au Bénin ;
- **calcule la surface** (ha), le périmètre et le centre (projection UTM 31N) ;
- refuse un contour qui chevauche une autre parcelle du même exploitant ;
- **ouvre automatiquement un litige** si le contour chevauche la parcelle d'un autre exploitant
  (au-delà de `LAND_OVERLAP_TOLERANCE_M2`, pour ignorer les bordures partagées) ;
- archive l'ancien contour à chaque modification (`PUT /lands/{id}/boundary`).

Les géométries sont renvoyées en **GeoJSON** (coordonnées `[longitude, latitude]`),
directement utilisables avec Leaflet, MapLibre ou OpenLayers :
`GET /lands/me/geojson`, `GET /lands/{id}/geojson`, `GET /state/map/lands?bbox=lon_min,lat_min,lon_max,lat_max`.

## Endpoints

| Module | Route | Accès |
|---|---|---|
| auth | `POST /auth/login-npi`, `GET /auth/me` | public / connecté |
| lands | `POST /lands/` | farmer |
| | `GET /lands/me`, `/lands/me/geojson` | connecté |
| | `GET·PATCH·DELETE /lands/{id}`, `PUT /lands/{id}/boundary`, `GET /lands/{id}/geojson` | propriétaire (lecture : + agent) |
| | `POST /lands/{id}/disputes` (signaler) | connecté, sauf le propriétaire |
| | `GET /lands/{id}/disputes` | propriétaire ou agent |
| | `POST·GET /lands/{id}/harvests` (récoltes réelles) | propriétaire (lecture : + agent) |
| | `GET /lands/disputes`, `PATCH /lands/disputes/{id}` | state_agent |
| monitoring | `POST /monitoring/diagnose` (photo + `land_id` ou département/commune, GPS facultatif, `language`) | connecté |
| | `GET /monitoring/diagnoses/me`, `/diagnoses/{id}`, `/diagnoses/{id}/audio` | auteur ou agent |
| | `GET /monitoring/weather?latitude&longitude`, `/weather-alerts/{commune}` | public |
| | `GET /monitoring/weather/land/{id}` | propriétaire ou agent |
| market | `GET /market/offers` (filtres commune, département, produit, prix max) | public |
| | `POST /market/offers` | farmer |
| | `GET /market/offers/me`, `PATCH /market/offers/{id}`, `PATCH /market/offers/{id}/status` | auteur |
| state | `GET /state/dashboard-metrics`, `/stats/zones`, `/stats/crops`, `/sanitary/hotspots`, `/map/lands`, `/map/alerts` | state_agent |
| knowledge | `GET /knowledge/categories`, `/guides`, `/guides/{slug}` | public |
| | `GET /knowledge/guides/{slug}/audio` | connecté |
| | `POST·PUT·DELETE /knowledge/guides` | state_agent |

Chaque offre contient `tel_url` et `whatsapp_url` (message pré-rempli) pour le bouton de contact.
La météo (Open-Meteo, sans clé) renvoie un résumé `color` vert/orange/rouge, un `pictogram`,
un message simple et les indicateurs `sowing_favorable` / `spraying_advised`.

## Limites connues

- La connexion vérifie le couple NPI + téléphone, pas l'identité réelle : ajoutez un code OTP par SMS
  ou une intégration avec l'identification nationale avant la production.
- Les fiches réglementaires fournies sont des **exemples** (`verified: false`) à faire valider
  par le MAEP ou les services habilités.
- Le résumé en fon ou yoruba est produit par Gemini : qualité à faire vérifier par des locuteurs.
  La voix de synthèse lit le texte tel quel ; elle est fiable en français.
- L'audio est renvoyé en WAV (≈ 50 Ko par seconde) : pour les connexions faibles, une conversion
  en Opus/MP3 (ffmpeg) serait préférable.
- Le cache météo est en mémoire : il est propre à chaque instance de l'API.
