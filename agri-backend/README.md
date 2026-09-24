# AgriSmart Benin API

## Démarrage

```bash
./init_env.sh              # génère .env avec des secrets aléatoires
# (optionnel) ajoutez GEMINI_API_KEY dans .env
docker compose up -d --build
```

Documentation interactive : http://localhost:8000/docs

## Authentification

1. `POST /api/v1/auth/login-npi` renvoie un jeton JWT.
2. Envoyez-le dans l'en-tête `Authorization: Bearer <jeton>`.

Le rôle `state_agent` ne peut pas être choisi à l'inscription :

```bash
docker compose exec api python -m app.scripts.promote_user <NPI> state_agent
```

## Droits d'accès

| Route | Accès |
|---|---|
| `POST /lands/`, `POST /market/offers` | farmer |
| `GET /lands/me`, `POST /monitoring/diagnose` | tout utilisateur connecté |
| `GET /lands/owner/{npi}` | le propriétaire ou state_agent |
| `GET /market/offers`, `GET /monitoring/weather-alerts/{commune}` | public |
| `GET /state/dashboard-metrics` | state_agent |

## Limites connues

La connexion vérifie le couple NPI + téléphone, mais pas encore l'identité réelle :
pour la production, ajoutez un code OTP par SMS ou une intégration avec les services
d'identification nationaux. La météo est encore simulée.
