# gdev_agri_gouv_bj
# AgriSmart Bénin

Plateforme numérique territoriale pour l'agriculture intelligente et la gestion foncière au Bénin (MAEP / ANDF).

Ce dépôt regroupe :
- `agri-backend` : API FastAPI (Python 3.12, asynchrone) + MongoDB 7 + Moteur SIG (UTM 31N) + Assistance IA (Gemini 2.5).
- `agri-frontend` : Application Web Progressive (PWA React 19, TypeScript, Tailwind CSS, MapLibre GL / Protomaps PMTiles).

---

## 🚀 Démarrage Rapide avec Docker Compose

Un fichier `docker-compose.yml` est disponible à la racine pour lancer **simultanément la base de données, le backend et le frontend**.

### 1. Initialiser l'environnement

Exécutez le script d'initialisation pour générer un fichier `.env` avec des secrets sécurisés (mot de passe MongoDB et clé JWT aléatoires) :

```bash
./init_env.sh
```

> **Optionnel :** Pour activer le diagnostic réel par photo et les fonctions d'assistant de culture, ajoutez votre clé d'API Gemini dans `.env` (`GEMINI_API_KEY=...`). Sans cette clé, la plateforme fonctionne en mode simulation dégradé.

### 2. Construire et démarrer les conteneurs

```bash
docker compose up -d --build
```

Cette commande démarre les 3 services :
- `mongodb` : Base de données NoSQL Mongo 7 avec index géospatiaux et TTL.
- `api` : Backend FastAPI accessible sur http://localhost:8000 (documentation Swagger sur http://localhost:8000/docs).
- `web` : Frontend React PWA servi par Nginx avec reverse proxy vers l'API, accessible sur **http://localhost:8080**.

### 3. Charger les données de démonstration

Pour initialiser la base avec ~200 parcelles réparties sur les 12 départements du Bénin et des comptes de test :

```bash
docker compose exec api python -m app.scripts.seed_demo
```

Pour réinitialiser complètement les données de démonstration :
```bash
docker compose exec api python -m app.scripts.seed_demo --reset
```

---

## 👥 Comptes de démonstration

La connexion s'effectue par NPI (Numéro Personnel d'Identification) et code SMS. En mode démonstration / développement, le code de connexion SMS s'affiche directement à l'écran.

| Rôle | NPI | Téléphone | Accès & Fonctionnalités |
|---|---|---|---|
| **Exploitant agricole** | `0100000001` | `0190000001` | Parcelles à Dangbo, cadastre, diagnostic photo, météo, conseiller de stockage, offres de récoltes. |
| **Acheteur** | `0100000002` | `0190000002` | Catalogue de produits, offres suivies, mise en relation directe WhatsApp / appel. |
| **Agent de l'État** | `0100000003` | `0190000003` | Vérification de parcelles, médiation de litiges, préparation des terres du domaine privé, veille sanitaire. |
| **Superviseur de l'État** | `0100000004` | `0190000004` | Cockpit national, publication des appels d'offres fonciers, validation des attributions de concessions. |

---

## 🗺️ Ports et Accès

- **Application web (PWA)** : [http://localhost:8080](http://localhost:8080)
- **Documentation API (Swagger UI)** : [http://localhost:8000/docs](http://localhost:8000/docs)
- **Vérification de l'état du service** : [http://localhost:8000/health](http://localhost:8000/health) ou [http://localhost:8080/health](http://localhost:8080/health)
- **Base de données MongoDB** : `localhost:27019`

---

## 🛑 Arrêt des services

```bash
docker compose down
```

Pour supprimer également les volumes persistants (remise à zéro de la base de données) :
```bash
docker compose down -v
```

---

## 📖 En savoir plus

- Voir [agri-backend/README.md](file:///home/gdev/Documents/GDEV/gdev_agri_gouv_bj/agri-backend/README.md) pour les détails techniques de l'API FastAPI et les tests unitaires.
- Voir [agri-frontend/README.md](file:///home/gdev/Documents/GDEV/gdev_agri_gouv_bj/agri-frontend/README.md) pour les détails sur la cartographie hors-ligne, PWA et composants React.
- Voir [agri-backend/FONCTIONNALITES.md](file:///home/gdev/Documents/GDEV/gdev_agri_gouv_bj/agri-backend/FONCTIONNALITES.md) pour l'inventaire exhaustif des fonctionnalités de la plateforme.