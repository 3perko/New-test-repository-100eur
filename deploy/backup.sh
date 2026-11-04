#!/usr/bin/env bash
# Záloha databázy a uložených súborov (číta .env z koreňa repozitára). Napr. denne cez cron:
#   15 2 * * * /opt/naklady/deploy/backup.sh >> /var/log/naklady-backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."
env_get() { [ -f .env ] && grep -E "^$1=" .env | tail -1 | cut -d= -f2- | tr -d '\r' || true; }
POSTGRES_USER=${POSTGRES_USER:-$(env_get POSTGRES_USER)}
POSTGRES_DB=${POSTGRES_DB:-$(env_get POSTGRES_DB)}
DEST=${BACKUP_DIR:-./backups}
STAMP=$(date +%Y%m%d-%H%M)
mkdir -p "$DEST"
docker compose exec -T db pg_dump -U "${POSTGRES_USER:-app}" -d "${POSTGRES_DB:-naklady}" -Fc > "$DEST/db-$STAMP.dump"
docker compose exec -T app tar czf - -C /app/data files > "$DEST/files-$STAMP.tar.gz"
find "$DEST" -type f -mtime +30 -delete
echo "Záloha hotová: $DEST/*-$STAMP.*"
