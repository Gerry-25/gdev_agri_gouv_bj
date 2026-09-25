# AgriSmart Benin API

Backend FastAPI + MongoDB du challenge Agriculture Intelligente.

## Démarrage

```bash
./init_env.sh                                           # .env avec secrets aléatoires
# (optionnel) GEMINI_API_KEY dans .env : diagnostic IA réel + lecture audio
docker compose up -d --build
docker compose exec api python -m app.scripts.seed_demo  # données de démonstration
```

- Application terrain : http://localhost:8080 ; espace agents : http://localhost:8080/agents/
  (nécessite le dossier `agri-frontend` à côté de `agri-backend`)
- Documentation interactive : http://localhost:8000/docs
- État du service : `GET /health`

### Comptes de démonstration

| Rôle | NPI | Téléphone |
|---|---|---|
| Exploitant (parcelles à Dangbo) | 0100000001 | 0190000001 |
| Acheteur | 0100000002 | 0190000002 |
| Agent de l'État | 0100000003 | 0190000003 |
| Superviseur de l'État | 0100000004 | 0190000004 |

`seed_demo --reset` régénère, `seed_demo --reset-only` supprime : seules les données marquées `is_demo` sont touchées.

### Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Les tests utilisent une base en mémoire ; l'IA, la météo et les requêtes géographiques
de MongoDB y sont simulées (voir `tests/conftest.py`).

## Guide pour le frontend

Le client TypeScript du frontend est généré depuis le contrat OpenAPI :
`python -m app.scripts.export_openapi > ../agri-frontend/openapi.json`, puis `npm run api:generate`
dans `agri-frontend`. À refaire après chaque modification d'une route ou d'un schéma.


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
Les rôles `state_agent` et `state_supervisor` s'attribuent avec
`python -m app.scripts.promote_user <NPI> state_agent|state_supervisor`.
Le superviseur a tous les droits d'un agent, plus la validation des décisions sensibles.

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
  `transfer_updated` (handshake), `land_verified` (check), `offer_interest` (buyer), `sanitary_alert` (bug),
  `call_published` / `call_updated` (megaphone), `call_awarded` (trophy), `contestation_filed` (law),
  `concession_active` / `concession_ended` (field), `concession_inspection` (check).
- Audio : `…/audio?format=mp3` (défaut, ≈ 4 Ko/s) ou `format=wav`.
- Images protégées : `image_url` d'un diagnostic exige l'en-tête `Authorization`.

## Domaine privé de l'État : attribution par appel à candidatures

La procédure suit la logique de la concession sur le domaine privé prévue par le Code foncier et domanial :
attribution à charge de mise en valeur selon un cahier des charges, pour une durée déterminée et contre une
redevance annuelle. **L'application prépare et trace la procédure ; l'acte officiel reste délivré par
l'autorité compétente**, et sa référence est enregistrée pour activer la concession.

| Étape | Qui | Route |
|---|---|---|
| Enregistrer la terre (contour GPS, référence du titre) | agent | `POST /domains` |
| Rédiger l'appel (cahier des charges, durée, redevance/ha, délai de mise en valeur, score minimal) | agent | `POST /domains/{id}/calls` |
| Publier (durée minimale de publicité ; exploitants éligibles notifiés) | superviseur **≠ rédacteur** | `POST /calls/{id}/publish` |
| Vérifier son éligibilité, candidater, retirer sa candidature | exploitant | `GET /calls/{id}/eligibility/me`, `POST·DELETE /calls/{id}/applications…` |
| Classement des candidatures (score figé au dépôt) | agent | `GET /calls/{id}/applications` |
| Proposer un lauréat après clôture, avec justification | agent | `POST /calls/{id}/award-proposal` |
| Valider ou refuser la proposition | superviseur **≠ auteur de la proposition** | `POST /calls/{id}/award-decision` |
| Contester pendant le délai | autres candidats | `POST /calls/{id}/contestations` |
| Trancher une contestation (fondée → attribution annulée) | superviseur | `PATCH /contestations/{id}` |
| Accepter ou se désister dans le délai | lauréat | `POST /calls/{id}/acceptance` |
| Enregistrer l'acte officiel → concession active | agent | `POST /concessions/{id}/official-act` |
| Déclarer les récoltes | titulaire | `POST /concessions/{id}/reports` |
| Inspections de mise en valeur, paiements de redevance | agent | `POST /concessions/{id}/inspections`, `/payments` |
| Retrait (défaut de mise en valeur, non-paiement…) ou fin | superviseur | `POST /concessions/{id}/termination` |
| Annuler ou déclarer l'appel infructueux | superviseur | `POST /calls/{id}/cancel`, `/unsuccessful` |

Garde-fous :
- un agent ne publie pas, et personne ne valide sa propre proposition (principe des « quatre yeux ») ;
- tout lauréat choisi hors de l'ordre du classement est signalé (`deviation_from_ranking`) ;
- l'acte ne peut être enregistré qu'après le délai de contestation et sans contestation ouverte ;
- une terre en litige ne peut pas faire l'objet d'un appel ; une parcelle privée qui empiète sur une terre
  de l'État ouvre automatiquement un litige ;
- chaque étape est horodatée dans l'historique de l'appel ; la vue publique (`GET /calls`) publie le
  cahier des charges, le nombre de candidats et le nom du lauréat retenu.

Les durées (publicité, contestation, acceptation) sont configurables dans `.env` et **doivent être
alignées sur les textes applicables** (Code foncier et domanial et ses décrets, pratiques de l'ANDF).

### Score de performance des exploitants

Score sur 100, détaillé critère par critère (`GET /performance/me`, `GET /state/farmers/performance`) :

| Critère | Poids | Calcul |
|---|---|---|
| Productivité | 40 % | rendement/ha comparé à la médiane de la même culture dans le même département (médiane = 50) |
| Fiabilité des prévisions | 15 % | écart moyen entre récolte prévue et réelle |
| Régularité | 15 % | stabilité d'une saison à l'autre (neutre à 50 avec moins de 2 saisons) |
| Conformité | 15 % | part des parcelles vérifiées, pénalités pour parcelle rejetée ou en litige |
| Marché | 15 % | ventes déclarées sur 12 mois |

Seules les récoltes sur parcelles **vérifiées par un agent** et les récoltes déclarées sur une concession
sont comptées. Éligibilité : au moins `PERFORMANCE_MIN_SEASONS` saisons et aucun litige ouvert.
Le calcul se fait à la demande ; à grande échelle, il faudra le précalculer par une tâche planifiée.

## Assistance IA

Toutes les fonctions d'IA passent par `app/core/ai_service.py`, qui applique quatre garanties :

- **l'IA propose, l'humain décide** : chaque sortie est journalisée (`ai_runs`) avec le modèle, la date et l'empreinte
  des données, et affichée avec le statut `proposition` ; attributions, vérifications, litiges et score restent des
  décisions humaines ;
- **aucune donnée personnelle envoyée à Gemini** : NPI, noms et téléphones sont retirés des contextes ; les parties
  d'un litige deviennent « partie A », « partie B » ;
- **coûts maîtrisés** : cache des réponses identiques (`AI_CACHE_DAYS`) et quota par utilisateur (`AI_DAILY_QUOTA_PER_USER`) ;
- **mode dégradé** : sans clé Gemini, les routes d'IA répondent 503 ; les calculs par règles (lecture du sol, risque de
  stockage, priorités d'inspection, prix conseillé) continuent de fonctionner.

| Fonction | Routes | Accès |
|---|---|---|
| Plan de mise en valeur d'une terre de l'État | `PUT /domains/{id}/survey`, `PUT /domains/{id}/orientation`, `POST /domains/{id}/photos`, `POST /domains/{id}/environment`, `GET /domains/{id}/readiness`, `POST /domains/{id}/plans`, `PATCH /domains/plans/{id}/review`, `GET /domains/plans/{id}/call-draft` | agent |
| Aide à l'analyse d'une candidature | `POST /calls/{id}/applications/{app_id}/ai-review` | agent |
| Sol et plan de fumure d'une parcelle | `GET·POST /lands/{id}/soil`, `POST·GET /lands/{id}/fertilization-plans`, `…/latest/audio` | propriétaire (lecture : + agent) |
| Assistant (texte et voix) | `POST /assistant/ask`, `POST /assistant/ask-voice`, `GET /assistant/history`, `GET /assistant/answers/{id}/audio` | connecté |
| Question de suivi sur un diagnostic | `POST /monitoring/diagnoses/{id}/ask` | auteur ou agent |
| Prix conseillé et brouillon d'annonce | `GET /market/price-suggestion`, `POST /market/offers/ai-draft` | public / farmer |
| Conseiller de stockage | `POST /storage/lots`, `GET /storage/lots/me`, `POST /storage/lots/{id}/checks`, `PATCH /storage/lots/{id}/status`, `POST /storage/lots/{id}/advice`, `GET /storage/overview` | farmer / agent |
| Synthèse neutre d'un litige | `POST /lands/disputes/{id}/ai-summary` | agent |
| Priorités d'inspection (règles, sans IA) | `GET /state/inspection-priorities` | agent |
| Note hebdomadaire | `POST·GET /state/reports/weekly`, `GET /state/reports` | agent |
| Analyse du suivi d'une concession | `POST /concessions/{id}/ai-review` | agent |

### Données environnementales des terres

Collectées automatiquement à partir du contour GPS (`app/core/environment/`), chaque source indépendamment :

| Source | Données | Configuration |
|---|---|---|
| iSDAsoil (30 m) | pH, carbone organique, N, P, K, texture…, avec incertitude, à 0-20 et 20-50 cm | `ISDA_USERNAME`, `ISDA_PASSWORD` (compte gratuit) |
| Open-Meteo archives | 10 ans de pluie et de températures, saisons des pluies, poches sèches | aucune |
| Open-Meteo Elevation | altitude, pente, position (plateau, versant, bas-fond) | aucune |
| OpenStreetMap (Overpass) | distances route, cours d'eau, marché | aucune |
| Zones agroécologiques | suggestion par commune ou département, **confirmée par l'agent** dans le relevé | — |

Le plan exige le profil environnemental, le relevé de terrain et les orientations de l'État ; les photos (jusqu'à 4
transmises à l'IA) et l'analyse de sol au laboratoire améliorent sa fiabilité. Un plan n'est montré aux candidats
qu'après **relecture par un expert** (INRAB, ATDA…) enregistrée par un autre agent que celui qui l'a généré.

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
| performance | `GET /performance/me` | connecté |
| | `GET /state/farmers/performance`, `/state/farmers/{npi}/performance` | agent |
| domaine de l'État | voir le tableau de la procédure ci-dessus ; `GET /calls`, `GET /calls/{id}` | public |
| | `GET /domains`, `/domains/geojson`, `/domains/{id}`, `PATCH /domains/{id}`, `GET /calls/manage`, `/calls/{id}/manage`, `/calls/{id}/contestations`, `GET /concessions` | agent |
| | `POST /domains/{id}/retire` | superviseur |
| | `GET /calls/applications/me`, `GET /concessions/me`, `GET /concessions/{id}` | connecté (titulaire ou agent) |
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
