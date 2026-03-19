#!/usr/bin/env sh
set -eu

if [ ! -f .env ]; then
  cp .env.example .env
  echo ".env created from .env.example"
else
  echo ".env already exists"
fi

echo "Next step: open .env and set TELEGRAM_BOT_TOKEN plus your LLM key."
