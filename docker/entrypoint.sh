#!/bin/bash
# GhostAttend — Bot Entrypoint
# Container başlarken veritabanı migration'larını (Alembic) otomatik çalıştırır.

set -e

echo "📦 Veritabanı tabloları güncelleniyor (Alembic upgrade head)..."
alembic upgrade head

echo "🚀 Bot başlatılıyor..."
exec "$@"
