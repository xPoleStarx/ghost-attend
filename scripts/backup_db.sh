#!/bin/bash
# GhostAttend — DB Backup Script
# Kullanım: ./scripts/backup_db.sh [backup_dir]

set -euo pipefail

BACKUP_DIR="${1:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/ghostattend_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "📦 Veritabanı yedeği alınıyor..."

docker compose exec -T postgres pg_dump \
    -U "${POSTGRES_USER:-ghost}" \
    -d ghostattend \
    --format=plain \
    --no-owner \
    | gzip > "$BACKUP_FILE"

echo "✅ Yedek kaydedildi: $BACKUP_FILE"

# 30 günden eski yedekleri sil
find "$BACKUP_DIR" -name "ghostattend_*.sql.gz" -mtime +30 -delete
echo "🧹 30 günden eski yedekler temizlendi."

# Boyutu göster
ls -lh "$BACKUP_FILE"
