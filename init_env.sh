#!/bin/bash
# Génère un fichier .env avec des secrets aléatoires à partir de .env.example
set -e
cd "$(dirname "$0")"

gen() { python3 -c "import secrets; print(secrets.token_hex($1))" 2>/dev/null || openssl rand -hex "$1"; }

if [ ! -f .env ]; then
    MONGO_PW=$(gen 24)
    JWT_SECRET=$(gen 32)

    sed -e "s/a_remplacer_par_un_mot_de_passe_fort/${MONGO_PW}/g" \
        -e "s/^JWT_SECRET_KEY=.*/JWT_SECRET_KEY=${JWT_SECRET}/" \
        .env.example > .env
    echo "[OK] Fichier .env généré à la racine avec des secrets aléatoires."
else
    echo "[!] .env racine existe déjà : rien n'est modifié."
fi

# Synchronise avec agri-backend/.env pour le développement local éventuel
if [ ! -f agri-backend/.env ]; then
    cp .env agri-backend/.env
    echo "[OK] Fichier agri-backend/.env synchronisé."
fi

echo "     (Optionnel) Renseignez GEMINI_API_KEY dans .env pour activer les fonctionnalités IA réelles."
