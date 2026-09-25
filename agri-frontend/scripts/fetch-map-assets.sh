#!/bin/bash
# Récupère les polices et icônes du fond de carte Protomaps (licences libres : Noto Sans OFL, icônes du projet).
# Elles sont embarquées dans l'application pour que la carte fonctionne hors ligne.
set -e
cd "$(dirname "$0")/../apps/web/public"
BASE="https://raw.githubusercontent.com/protomaps/basemaps-assets/main"
mkdir -p map-assets/sprites map-assets/fonts
for f in light.json light.png light@2x.json light@2x.png; do
  curl -sf "$BASE/sprites/v4/$f" -o "map-assets/sprites/$f"
done
# Plages Unicode : latin, latin étendu (accents), API (ɔ, ɛ du fɔngbè), latin étendu additionnel, ponctuation
for font in "Noto Sans Regular" "Noto Sans Medium" "Noto Sans Italic"; do
  mkdir -p "map-assets/fonts/$font"
  for r in 0-255 256-511 512-767 7680-7935 8192-8447; do
    curl -sf "$BASE/fonts/${font// /%20}/$r.pbf" -o "map-assets/fonts/$font/$r.pbf"
  done
done
echo "[OK] Polices et icônes de carte dans apps/web/public/map-assets"
