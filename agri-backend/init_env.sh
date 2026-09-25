#!/bin/bash
# Génère un fichier .env avec des secrets aléatoires à partir de .env.example
set -e
cd "$(dirname "$0")"

if [ -f .env ]; then
    echo "[!] .env existe déjà : rien n'est modifié."
    exit 0
fi

gen() { python3 -c "import secrets; print(secrets.token_hex($1))" 2>/dev/null || openssl rand -hex "$1"; }
MONGO_PW=$(gen 24)
JWT_SECRET=$(gen 32)

sed -e "s/a_remplacer_par_un_mot_de_passe_fort/${MONGO_PW}/g" \
    -e "s/^JWT_SECRET_KEY=.*/JWT_SECRET_KEY=${JWT_SECRET}/" \
    .env.example > .env

echo "[OK] .env généré avec un mot de passe MongoDB et un secret JWT aléatoires."
echo "     Ajoutez votre GEMINI_API_KEY dans .env pour activer le diagnostic IA réel."
