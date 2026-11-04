#!/usr/bin/env bash
# Záloha databázy a uložených súborov. Spúšťajte z koreňa repozitára, napr. denne cez cron:
#   15 2 * * * cd /opt/naklady && ./deploy/backup.sh >> /var/log/naklady-backup.log 2>&1
set -euo pipefail
DEST=${BACKUP_DIR:-./backups}
STAMP=$(date +%Y%m%d-%H%M)
mkdir -p "$DEST"
docker compose exec -T db pg_dump -U "${POSTGRES_USER:-app}" -d "${POSTGRES_DB:-naklady}" -Fc > "$DEST/db-$STAMP.dump"
docker compose exec -T app tar czf - -C /app/data files > "$DEST/files-$STAMP.tar.gz"
find "$DEST" -type f -mtime +30 -delete
echo "Záloha hotová: $DEST/*-$STAMP.*"
