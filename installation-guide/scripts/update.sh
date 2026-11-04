#!/usr/bin/env bash
# Bezpečná aktualizácia: záloha → stiahnutie novej verzie → prebudovanie a reštart → kontrola.
# Databázové migrácie sa spustia automaticky pri štarte kontajnera app.
# Použitie: ./installation-guide/scripts/update.sh [ďalšie compose súbory, napr. -f docker-compose.prod.yml]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

COMPOSE=(docker compose -f docker-compose.yml "$@")

echo ">> 1/4 Záloha"
./deploy/backup.sh

echo ">> 2/4 Nová verzia z gitu"
git pull --ff-only

echo ">> 3/4 Prebudovanie a reštart"
"${COMPOSE[@]}" up -d --build

echo ">> 4/4 Kontrola"
sleep 8
"$ROOT/installation-guide/scripts/check-install.sh"
