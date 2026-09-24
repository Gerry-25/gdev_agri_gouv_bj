# AgriSmart Benin API

Backend FastAPI + MongoDB du challenge Agriculture Intelligente.

## Démarrage

```bash
./init_env.sh                                           # .env avec secrets aléatoires
# (optionnel) GEMINI_API_KEY dans .env : diagnostic IA réel + lecture audio
docker compose up -d --build
docker compose exec api python -m app.scripts.seed_demo  # données de démonstration
```

- Documentation interactive : http://localhost:8000/docs
- État du service : `GET /health`

### Comptes de démonstration

| Rôle | NPI | Téléphone |
|---|---|---|
| Exploitant (parcelles à Dangbo) | 0100000001 | 0190000001 |
| Acheteur | 0100000002 | 0190000002 |
| Agent de l'État | 0100000003 | 0190000003 |

`seed_demo --reset` régénère, `seed_demo --reset-only` supprime : seules les données marquées `is_demo` sont touchées.

### Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Les tests utilisent une base en mémoire ; l'IA, la météo et les requêtes géographiques
de MongoDB y sont simulées (voir `tests/conftest.py`).

## Guide pour le frontend

Toutes les routes sont préfixées par `/api/v1`. Les erreurs renvoient `{"detail": "..."}` avec un message
en français prêt à afficher (ou une liste de champs invalides pour les erreurs 422 de validation).

### Connexion par code SMS

1. `POST /auth/otp/request` `{npi, phone}` (+ `full_name`, `role`, `preferred_language` à la première connexion).
   La réponse indique `is_new_user`, `resend_in` et, **en mode simulation**, `simulated_code` à afficher à l'écran.
2. `POST /auth/otp/verify` `{npi, code}` renvoie `access_token` (1 h), `refresh_token` (30 jours) et le profil.
3. Envoyer `Authorization: Bearer <access_token>`. Sur une réponse 401, appeler `POST /auth/refresh`
   `{refresh_token}` : un **nouveau** couple de jetons est renvoyé (l'ancien refresh token devient invalide).
4. `POST /auth/logout` `{refresh_token}` ou `POST /auth/logout-all`.

Limites : 1 code par minute, 5 par heure, 5 essais par code. Réponses 429 avec en-tête `Retry-After`.
Le rôle `state_agent` s'attribue avec `python -m app.scripts.promote_user <NPI> state_agent`.

### Mode hors ligne

- Générer un `client_ref` (UUID) **au moment de la saisie** et le conserver dans la file d'attente.
  Si l'envoi est rejoué, l'API renvoie la ressource déjà créée (code 200 au lieu de 201) :
  parcelles (`POST /lands/`), offres (`POST /market/offers`), diagnostics (`POST /monitoring/diagnose`).
- Pour un diagnostic différé, envoyer `captured_at` (date de la photo, ISO 8601, 30 jours maximum).
- Compresser les photos dans le téléphone avant envoi (5 Mo maximum ; 1500 px suffisent).

### Parcelles par contour GPS

L'exploitant fait le tour de son champ ; envoyer les points **dans l'ordre** :

```json
POST /lands/
{
  "department": "Ouémé", "commune": "Dangbo", "locality": "Houédomè",
  "crop_type": "Manioc", "estimated_yield_kg": 8000, "client_ref": "3f6c1d2e-…",
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

Le serveur referme et valide le polygone, **calcule la surface**, refuse un chevauchement avec une autre
parcelle du même exploitant et **ouvre un litige** en cas de chevauchement avec un autre exploitant.
La réponse contient `warnings` (précision GPS faible, contour trop sommaire) à afficher à l'utilisateur.

Les géométries sont en **GeoJSON** `[longitude, latitude]`, compatibles Leaflet / MapLibre / OpenLayers.

### Codes utiles à l'interface

- Couleurs d'alerte : `green`, `yellow`, `orange`, `red`.
- Pictogrammes météo : `sun`, `rain`, `rain_heavy`, `wind`, `heat`, `seed`.
- Pictogrammes des fiches : `forbidden`, `shield`, `law`, `sprout`, `question`, `calendar`, `leaf`, `map`, `info`.
- Notifications (`type` / `pictogram`) : `dispute_opened` / `dispute_updated` (law), `transfer_requested` /
  `transfer_updated` (handshake), `land_verified` (check), `offer_interest` (buyer), `sanitary_alert` (bug).
- Audio : `…/audio?format=mp3` (défaut, ≈ 4 Ko/s) ou `format=wav`.
- Images protégées : `image_url` d'un diagnostic exige l'en-tête `Authorization`.

## Endpoints

| Module | Route | Accès |
|---|---|---|
| auth | `POST /auth/otp/request`, `/auth/otp/verify`, `/auth/refresh`, `/auth/logout` | public |
| | `GET·PATCH /auth/me`, `POST /auth/logout-all` | connecté |
| lands | `POST /lands/` | farmer |
| | `GET /lands/me`, `/lands/me/geojson`, `/lands/transfers/me` | connecté |
| | `GET /lands/{id}`, `/lands/{id}/geojson`, `/lands/{id}/disputes`, `/lands/{id}/harvests`, `/lands/{id}/transfers` | propriétaire ou agent |
| | `PATCH·DELETE /lands/{id}`, `PUT /lands/{id}/boundary`, `POST /lands/{id}/harvests`, `POST /lands/{id}/transfers` | propriétaire |
| | `POST /lands/{id}/disputes` | connecté, sauf le propriétaire |
| | `PATCH /lands/transfers/{id}` | agent (approuver/rejeter) ou demandeur (annuler) |
| | `GET /lands/disputes`, `PATCH /lands/disputes/{id}`, `GET /lands/transfers`, `PATCH /lands/{id}/verification` | state_agent |
| monitoring | `POST /monitoring/diagnose` | connecté |
| | `GET /monitoring/diagnoses/me`, `/diagnoses/{id}`, `/diagnoses/{id}/image`, `/diagnoses/{id}/audio` | auteur ou agent |
| | `GET /monitoring/weather?latitude&longitude`, `/weather-alerts/{commune}` | public |
| | `GET /monitoring/weather/land/{id}` | propriétaire ou agent |
| market | `GET /market/offers`, `/market/offers/{id}`, `/market/prices` | public |
| | `POST /market/offers` | farmer |
| | `GET /market/offers/me`, `PATCH /market/offers/{id}`, `PATCH /market/offers/{id}/status` | auteur |
| | `POST /market/offers/{id}/interest` | connecté, sauf l'auteur |
| | `GET /market/offers/{id}/interests` | auteur ou agent |
| state | `GET /state/dashboard-metrics`, `/stats/zones`, `/stats/crops`, `/sanitary/hotspots`, `/map/lands`, `/map/alerts` | state_agent |
| knowledge | `GET /knowledge/categories`, `/guides`, `/guides/{slug}` | public |
| | `GET /knowledge/guides/{slug}/audio` | connecté |
| | `POST·PUT·DELETE /knowledge/guides` | state_agent |
| notifications | `GET /notifications/me`, `/me/unread-count`, `POST /me/read-all`, `PATCH /{id}/read` | connecté |

## Brancher un vrai fournisseur SMS

Ajouter dans `app/core/sms.py` une classe avec `name`, `exposes_code = False` et une méthode
`async send(phone, text)`, la sélectionner dans `get_sms_sender()` et ajouter sa valeur au type de
`SMS_PROVIDER` dans `app/core/config.py`. Aucune autre partie du code n'est à modifier.
`APP_ENV=production` refuse de démarrer tant que le SMS est simulé.

## Limites connues

- Les requêtes géographiques de MongoDB (`$geoIntersects`, `$geoWithin`) ne sont pas couvertes par les tests
  automatiques : vérifier la détection des chevauchements et les filtres `bbox` sur la vraie base.
- Les fiches réglementaires fournies sont des **exemples** (`verified: false`) à faire valider par le MAEP.
- Les résumés en fon et yoruba sont produits par Gemini : à faire vérifier par des locuteurs.
- Les coordonnées des communes du script de démonstration sont approximatives.
- Le cache météo est en mémoire : il est propre à chaque instance de l'API.
- Pas d'alerte météo poussée automatiquement (il faudrait une tâche planifiée) : le frontend interroge la météo.
