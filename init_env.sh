#!/bin/bash
# Génère un fichier .env avec des secrets aléatoires respectant le format d'AgriSmart Bénin
set -e
cd "$(dirname "$0")"

FORCE=false
if [ "$1" = "--force" ] || [ "$1" = "-f" ]; then
    FORCE=true
fi

gen() { python3 -c "import secrets; print(secrets.token_hex($1))" 2>/dev/null || openssl rand -hex "$1"; }

EXISTING_GEMINI_KEY=""
EXISTING_ISDA_USER=""
EXISTING_ISDA_PASS=""
EXISTING_ESRI_TOKEN=""
if [ -f .env ]; then
    EXISTING_GEMINI_KEY=$(grep -E '^GEMINI_API_KEY=' .env 2>/dev/null | cut -d '=' -f2- || true)
    EXISTING_ISDA_USER=$(grep -E '^ISDA_USERNAME=' .env 2>/dev/null | cut -d '=' -f2- || true)
    EXISTING_ISDA_PASS=$(grep -E '^ISDA_PASSWORD=' .env 2>/dev/null | cut -d '=' -f2- || true)
    EXISTING_ESRI_TOKEN=$(grep -E '^VITE_ESRI_TOKEN=' .env 2>/dev/null | cut -d '=' -f2- || true)
fi

GEMINI_KEY="${GEMINI_API_KEY:-$EXISTING_GEMINI_KEY}"
ISDA_USER="${ISDA_USERNAME:-$EXISTING_ISDA_USER}"
ISDA_PASS="${ISDA_PASSWORD:-$EXISTING_ISDA_PASS}"
ESRI_TOKEN="${VITE_ESRI_TOKEN:-$EXISTING_ESRI_TOKEN}"

if [ ! -f .env ] || [ "$FORCE" = true ]; then
    MONGO_PW=$(gen 24)
    JWT_SECRET=$(gen 32)

    cat <<EOF > .env
# Configuration AgriSmart Bénin
# Copiez ce fichier en .env (ou lancez ./init_env.sh pour générer des secrets aléatoires)
APP_ENV=development
PROJECT_NAME="AgriSmart Benin API"
API_V1_STR="/api/v1"

# Identifiants MongoDB (utilisés par docker compose)
MONGO_ROOT_USER=admin
MONGO_ROOT_PASSWORD=${MONGO_PW}

# URL MongoDB (utilisée hors Docker ; en Docker, docker compose la remplace automatiquement)
MONGODB_URL="mongodb://admin:${MONGO_PW}@localhost:27019/?authSource=admin"
DATABASE_NAME="agri_smart_db"

# Secret de signature des jetons JWT (32 caractères minimum)
JWT_SECRET_KEY=${JWT_SECRET}
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=30

# Code de connexion par SMS : "simulation" renvoie le code dans la réponse (affiché par le frontend)
SMS_PROVIDER=simulation
OTP_TTL_SECONDS=300
OTP_RESEND_SECONDS=60
OTP_MAX_PER_HOUR=5
OTP_MAX_ATTEMPTS=5

# Laisser vide pour utiliser le mode simulation du diagnostic IA
GEMINI_API_KEY=${GEMINI_KEY}
GEMINI_MODEL=gemini-3.1-flash-lite

# Origines autorisées pour le frontend, séparées par des virgules
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://localhost:8080

MAX_UPLOAD_SIZE_MB=5
STATE_REVENUE_RATE=0.015

# Lecture audio (Gemini TTS) - modèle et voix configurables
GEMINI_TTS_MODEL=gemini-3.8-flash-tts
TTS_VOICE=Kore

# Parcelles : chevauchement toléré (m²) dû à l'imprécision GPS des téléphones
LAND_OVERLAP_TOLERANCE_M2=25

# Veille sanitaire : nombre de cas dans une commune pour déclarer un foyer
HOTSPOT_MIN_CASES=3
HOTSPOT_WINDOW_DAYS=30

# Score de performance : saisons de récolte vérifiées requises pour candidater
PERFORMANCE_MIN_SEASONS=2

# Appels à candidatures sur le domaine privé de l'État (à ajuster selon les textes en vigueur)
CALL_MIN_OPEN_DAYS=15
CALL_CONTEST_DAYS=15
AWARD_ACCEPTANCE_DAYS=15
MAX_ACTIVE_CONCESSIONS_PER_FARMER=1

# --- Assistance IA
# Modèle plus puissant pour les plans de mise en valeur des terres de l'État
GEMINI_PLAN_MODEL=gemini-3.1-flash-lite
# Appels IA (hors cache) par utilisateur et par 24 h
AI_DAILY_QUOTA_PER_USER=40
# L'assistant ne répond qu'à partir des fiches validées ; true seulement pour une démonstration
ASSISTANT_INCLUDE_UNVERIFIED=false
# Filières soutenues par l'État, transmises à l'IA (à tenir à jour)
SUBSIDIZED_CROPS=Riz,Coton,Soja,Anacarde

# --- Données de sol iSDAsoil (gratuit, compte à créer sur https://isda-africa.com/api/registration)
ISDA_USERNAME=${ISDA_USER}
ISDA_PASSWORD=${ISDA_PASS}

# --- Frontend : vue satellite Esri (compte développeur ArcGIS Location Platform gratuit)
VITE_ESRI_TOKEN=${ESRI_TOKEN}
EOF

    echo "[OK] Fichier .env généré avec succès avec les modèles Gemini actuels et des secrets aléatoires."
else
    echo "[!] .env racine existe déjà : rien n'est modifié. Utilisez './init_env.sh --force' pour régénérer."
fi

# Synchronise avec agri-backend/.env pour le développement local éventuel
cp .env agri-backend/.env
echo "[OK] Fichier agri-backend/.env synchronisé."

if [ -z "${GEMINI_KEY}" ]; then
    echo "     (Optionnel) Renseignez GEMINI_API_KEY dans .env pour activer les fonctionnalités IA réelles."
fi
