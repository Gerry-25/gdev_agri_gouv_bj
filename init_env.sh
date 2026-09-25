#!/bin/bash
# ==============================================================================
# AgriSmart Bénin - Script d'initialisation et de mise à jour de l'environnement
# ==============================================================================
# Génère ou met à jour le fichier .env racine et le synchronise avec agri-backend/.env
# Préserve vos secrets existants tout en garantissant la compatibilité des modèles
# Gemini et des paramètres requis pour éviter toute régression.
# ==============================================================================
set -e
cd "$(dirname "$0")"

FORCE=false
CHECK_ONLY=false

for arg in "$@"; do
    case "$arg" in
        --force|-f)
            FORCE=true
            ;;
        --check|-c)
            CHECK_ONLY=true
            ;;
        --help|-h)
            echo "Usage: ./init_env.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  (sans option)     Initialise .env s'il est absent, ou met à jour les clés/modèles obsolètes s'il existe."
            echo "  --force, -f       Régénère un .env neuf à partir de .env.example (sauvegarde l'ancien et conserve GEMINI_API_KEY)."
            echo "  --check, -c       Vérifie la conformité de .env sans modifier aucun fichier."
            echo "  --help, -h        Affiche cette aide."
            exit 0
            ;;
    esac
done

gen() {
    python3 -c "import secrets; print(secrets.token_hex($1))" 2>/dev/null || openssl rand -hex "$1"
}

if [ ! -f .env ] || [ "$FORCE" = true ]; then
    PREV_GEMINI_KEY=""
    if [ -f .env ] && [ "$FORCE" = true ]; then
        BACKUP_FILE=".env.bak.$(date +%Y%m%d%H%M%S)"
        cp .env "$BACKUP_FILE"
        PREV_GEMINI_KEY=$(grep -E "^GEMINI_API_KEY=" .env | cut -d'=' -f2- || true)
        echo "[*] Sauvegarde de l'ancien .env créée : $BACKUP_FILE"
    fi

    MONGO_PW=$(gen 24)
    JWT_SECRET=$(gen 32)

    sed -e "s/a_remplacer_par_un_mot_de_passe_fort/${MONGO_PW}/g" \
        -e "s/^JWT_SECRET_KEY=.*/JWT_SECRET_KEY=${JWT_SECRET}/" \
        .env.example > .env

    # Si une clé Gemini existait avant le force, la réinjecter
    if [ -n "$PREV_GEMINI_KEY" ] && [ "$PREV_GEMINI_KEY" != "" ]; then
        python3 -c "
import sys
with open('.env', 'r', encoding='utf-8') as f:
    c = f.read()
import re
c = re.sub(r'^GEMINI_API_KEY=.*', 'GEMINI_API_KEY=$PREV_GEMINI_KEY', c, flags=re.M)
with open('.env', 'w', encoding='utf-8') as f:
    f.write(c)
"
        echo "[OK] Clé GEMINI_API_KEY existante conservée."
    fi

    echo "[OK] Fichier .env généré à la racine avec des secrets aléatoires et modèles Gemini à jour."
else
    # Le fichier .env existe : vérifier et corriger les régressions / modèles obsolètes
    python3 - "$CHECK_ONLY" << 'EOF'
import re, sys

check_only = sys.argv[1].lower() == "true"
env_file = ".env"
example_file = ".env.example"

with open(env_file, "r", encoding="utf-8") as f:
    env_content = f.read()

with open(example_file, "r", encoding="utf-8") as f:
    example_lines = f.readlines()

changes = []

# 1. Modèles Gemini à jour (remplacement des versions 2.5 dépréciées par la configuration actuelle)
model_updates = {
    r"^GEMINI_MODEL=.*": "GEMINI_MODEL=gemini-3.1-flash-lite",
    r"^GEMINI_TTS_MODEL=.*": "GEMINI_TTS_MODEL=gemini-3.8-flash-tts",
    r"^GEMINI_PLAN_MODEL=.*": "GEMINI_PLAN_MODEL=gemini-3.1-flash-lite",
}

for pattern, new_val in model_updates.items():
    match = re.search(pattern, env_content, re.M)
    if match:
        old_val = match.group(0)
        # Remplacer si modèle déprécié 2.5 ou preview
        if "gemini-2.5" in old_val or "preview" in old_val:
            env_content = re.sub(pattern, new_val, env_content, flags=re.M)
            changes.append(f"  - Modèle mis à jour : {old_val} -> {new_val}")
    else:
        env_content += f"\n{new_val}\n"
        changes.append(f"  - Variable ajoutée : {new_val}")

# 2. Vérification CORS (doit inclure 8080 pour le conteneur web de production/démo)
cors_match = re.search(r"^CORS_ORIGINS=(.*)", env_content, re.M)
if cors_match:
    cors_val = cors_match.group(1).strip()
    if "8080" not in cors_val:
        new_cors = f"{cors_val},http://localhost:8080"
        env_content = re.sub(r"^CORS_ORIGINS=.*", f"CORS_ORIGINS={new_cors}", env_content, flags=re.M)
        changes.append(f"  - CORS mis à jour pour autoriser le port 8080 : {new_cors}")
else:
    env_content += "\nCORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://localhost:8080\n"
    changes.append("  - CORS_ORIGINS ajouté avec port 8080")

# 3. Clés manquantes présentes dans .env.example
existing_keys = set(re.findall(r"^([A-Z0-9_]+)=", env_content, re.M))
missing_keys = []
for line in example_lines:
    m = re.match(r"^([A-Z0-9_]+)=(.*)", line.strip())
    if m:
        k, v = m.group(1), m.group(2)
        if k not in existing_keys and not k.startswith("MONGO_ROOT_PASSWORD") and not k.startswith("JWT_SECRET_KEY"):
            missing_keys.append(f"{k}={v}")

if missing_keys:
    env_content += "\n# Variables additionnelles ajoutées automatiquement depuis .env.example\n"
    for item in missing_keys:
        env_content += f"{item}\n"
        changes.append(f"  - Clé manquante ajoutée : {item}")

if changes:
    if check_only:
        print("[!] Incohérences détectées dans votre .env :")
        for c in changes:
            print(c)
        print("    Exécutez ./init_env.sh pour appliquer automatiquement ces corrections.")
    else:
        with open(env_file, "w", encoding="utf-8") as f:
            f.write(env_content)
        print("[OK] Fichier .env mis à jour avec succès :")
        for c in changes:
            print(c)
else:
    print("[OK] Fichier .env déjà conforme et à jour (aucun conflit détecté).")
EOF
fi

if [ "$CHECK_ONLY" = false ]; then
    # Synchronise avec agri-backend/.env
    cp -f .env agri-backend/.env
    echo "[OK] Fichier agri-backend/.env synchronisé avec le .env racine."
fi

echo ""
echo "État de la configuration :"
echo "  - Backend API  : http://localhost:8000"
echo "  - Frontend Web : http://localhost:8080"
if grep -qE "^GEMINI_API_KEY=[A-Za-z0-9_.-]{10,}" .env; then
    echo "  - IA Gemini    : Activée (clé configurée)"
else
    echo "  - IA Gemini    : Mode simulation (renseignez GEMINI_API_KEY dans .env pour l'IA réelle)"
fi
