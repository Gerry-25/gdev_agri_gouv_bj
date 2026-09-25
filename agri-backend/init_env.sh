#!/bin/bash
# Génère un fichier .env avec des secrets aléatoires à partir de .env.example
set -e
cd "$(dirname "$0")"

FORCE=false
if [ "$1" = "--force" ] || [ "$1" = "-f" ]; then
    FORCE=true
fi

# Si le .env racine existe, on le copie simplement
if [ -f ../.env ]; then
    cp ../.env .env
    echo "[OK] .env synchronisé depuis la racine du projet."
    exit 0
fi

if [ -f .env ] && [ "$FORCE" != true ]; then
    echo "[!] .env existe déjà : rien n'est modifié. Utilisez './init_env.sh --force' pour régénérer."
    exit 0
fi

EXISTING_GEMINI_KEY=""
if [ -f .env ]; then
    EXISTING_GEMINI_KEY=$(grep -E '^GEMINI_API_KEY=' .env 2>/dev/null | cut -d '=' -f2- || true)
fi
GEMINI_KEY="${GEMINI_API_KEY:-$EXISTING_GEMINI_KEY}"

gen() { python3 -c "import secrets; print(secrets.token_hex($1))" 2>/dev/null || openssl rand -hex "$1"; }
MONGO_PW=$(gen 24)
JWT_SECRET=$(gen 32)

sed -e "s/a_remplacer_par_un_mot_de_passe_fort/${MONGO_PW}/g" \
    -e "s/^JWT_SECRET_KEY=.*/JWT_SECRET_KEY=${JWT_SECRET}/" \
    -e "s/^GEMINI_API_KEY=.*/GEMINI_API_KEY=${GEMINI_KEY}/" \
    .env.example > .env

echo "[OK] .env généré avec un mot de passe MongoDB et un secret JWT aléatoires."
if [ -z "${GEMINI_KEY}" ]; then
    echo "     Ajoutez votre GEMINI_API_KEY dans .env pour activer le diagnostic IA réel."
fi
