#!/usr/bin/env bash
# Obnova zo zálohy vytvorenej deploy/backup.sh (aj pri presune z vlastného počítača do cloudu).
# PREPÍŠE aktuálnu databázu a uložené súbory! Vyžaduje potvrdenie (alebo --yes).
# Použitie: ./installation-guide/scripts/restore.sh backups/db-RRRRMMDD-HHMM.dump [backups/files-RRRRMMDD-HHMM.tar.gz] [--yes]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

DB_DUMP="" FILES="" YES=0
for a in "$@"; do
  case "$a" in
    --yes) YES=1 ;;
    *.dump) DB_DUMP="$a" ;;
    *.tar.gz) FILES="$a" ;;
    *) echo "Neznámy parameter: $a" >&2; exit 2 ;;
  esac
done
[ -z "$DB_DUMP" ] && { echo "Zadajte súbor zálohy databázy (*.dump)." >&2; exit 2; }
[ -f "$DB_DUMP" ] || { echo "Súbor $DB_DUMP neexistuje." >&2; exit 1; }
[ -n "$FILES" ] && [ ! -f "$FILES" ] && { echo "Súbor $FILES neexistuje." >&2; exit 1; }

env_get() { [ -f .env ] && grep -E "^$1=" .env | tail -1 | cut -d= -f2- | tr -d '\r' || true; }
PGU="$(env_get POSTGRES_USER)"; PGU="${PGU:-app}"
PGD="$(env_get POSTGRES_DB)"; PGD="${PGD:-naklady}"

if [ "$YES" -ne 1 ]; then
  read -r -p "Naozaj prepísať databázu '$PGD'${FILES:+ a uložené súbory}? Napíšte ANO: " c
  [ "$c" = "ANO" ] || { echo "Zrušené."; exit 1; }
fi

docker compose up -d db
until docker compose exec -T db pg_isready -U "$PGU" -d "$PGD" >/dev/null 2>&1; do sleep 2; done
docker compose stop app scheduler >/dev/null 2>&1 || true

echo ">> Obnovujem databázu z $DB_DUMP"
docker compose exec -T db pg_restore -U "$PGU" -d "$PGD" --clean --if-exists --no-owner < "$DB_DUMP"

if [ -n "$FILES" ]; then
  echo ">> Obnovujem súbory z $FILES"
  docker compose run --rm -T --no-deps --entrypoint sh app -c "rm -rf /app/data/files && mkdir -p /app/data && tar xzf - -C /app/data" < "$FILES"
fi

docker compose up -d
echo "OK: obnova dokončená. Overte: ./installation-guide/scripts/check-install.sh"
