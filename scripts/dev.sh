#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.dev.yml}"

if docker compose version >/dev/null 2>&1; then
    COMPOSE=(docker compose -f "$COMPOSE_FILE")
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE=(docker-compose -f "$COMPOSE_FILE")
else
    echo "docker compose bulunamadi." >&2
    exit 1
fi

usage() {
    cat <<'EOF'
GhostAttend dev helper

Kullanim:
  ./scripts/dev.sh up
  ./scripts/dev.sh rebuild
  ./scripts/dev.sh down
  ./scripts/dev.sh logs
  ./scripts/dev.sh ps
  ./scripts/dev.sh migrate
  ./scripts/dev.sh test
  ./scripts/dev.sh reset
  ./scripts/dev.sh help
EOF
}

cmd="${1:-help}"

case "$cmd" in
    up)
        "${COMPOSE[@]}" up -d
        ;;
    rebuild)
        "${COMPOSE[@]}" up -d --build --force-recreate bot worker scheduler
        ;;
    down)
        "${COMPOSE[@]}" down
        ;;
    logs)
        "${COMPOSE[@]}" logs -f bot worker scheduler
        ;;
    ps)
        "${COMPOSE[@]}" ps
        ;;
    migrate)
        "${COMPOSE[@]}" run --rm bot alembic upgrade head
        ;;
    test)
        "${COMPOSE[@]}" run --rm bot python -m pytest tests/unit tests/integration -v
        ;;
    reset)
        "${COMPOSE[@]}" down -v
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        echo "Bilinmeyen komut: $cmd" >&2
        usage
        exit 1
        ;;
esac
