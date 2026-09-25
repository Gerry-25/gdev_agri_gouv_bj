#!/bin/bash
# Construit le fond de carte vectoriel du Bénin (données OpenStreetMap, ODbL) à partir d'une
# construction quotidienne Protomaps. Nécessite l'outil « pmtiles » : https://github.com/protomaps/go-pmtiles/releases
#
# Usage : ./scripts/build-benin-tiles.sh [AAAAMMJJ]
# Les dates disponibles sont listées sur https://maps.protomaps.com/builds
set -e
DATE="${1:-$(date -u -d 'yesterday' +%Y%m%d)}"
OUT="$(dirname "$0")/../apps/web/public/tiles/benin.pmtiles"
mkdir -p "$(dirname "$OUT")"
# Emprise du Bénin avec une petite marge ; zoom 15 suffit pour situer un champ
pmtiles extract "https://build.protomaps.com/${DATE}.pmtiles" "$OUT" --bbox=0.70,6.00,3.90,12.50 --maxzoom=15
ls -lh "$OUT"
echo "[OK] Fond de carte prêt. Pensez à mentionner « © OpenStreetMap » (déjà affiché par l'application)."
