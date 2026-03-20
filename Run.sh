#!/usr/bin/env bash
# GhostMyShit: venv olusturur, bagimliliklari kurar, Telegram botunu baslatir.
# Kullanim: chmod +x Run.sh && ./Run.sh
# Ortam: GHOST_MYSHIT_PYTHON=/tam/yol/python3 (istege bagli; old: GHOST_ATTEND_PYTHON da desteklenir)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

INSTALL_ONLY=false
SKIP_INSTALL=false
FORCE_INSTALL=false
NON_INTERACTIVE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-only) INSTALL_ONLY=true ;;
    --skip-install) SKIP_INSTALL=true ;;
    --force-install) FORCE_INSTALL=true ;;
    --non-interactive) NON_INTERACTIVE=true ;;
    *) echo "Bilinmeyen arguman: $1"; exit 1 ;;
  esac
  shift
done

step() { echo ""; echo "==> $1"; }

find_python() {
  if [[ -n "${GHOST_MYSHIT_PYTHON:-}" ]] && [[ -x "${GHOST_MYSHIT_PYTHON}" ]]; then
    echo "${GHOST_MYSHIT_PYTHON}"
    return 0
  fi
  if [[ -n "${GHOST_ATTEND_PYTHON:-}" ]] && [[ -x "${GHOST_ATTEND_PYTHON}" ]]; then
    echo "${GHOST_ATTEND_PYTHON}"
    return 0
  fi
  for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
      echo "$(command -v "$cmd")"
      return 0
    fi
  done
  for p in /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if [[ -x "$p" ]]; then echo "$p"; return 0; fi
  done
  return 1
}

VENV_PY="${ROOT}/.venv/bin/python"

if [[ "$SKIP_INSTALL" == true ]] && [[ ! -x "$VENV_PY" ]]; then
  echo "[!] .venv yok. Once: ./Run.sh (SkipInstall olmadan)" >&2
  exit 1
fi

if [[ ! -x "$VENV_PY" ]]; then
  step "Sanal ortam (.venv) yok; sistem Python araniyor..."
  if ! SYS_PY="$(find_python)"; then
    cat >&2 << 'EOF'
[!] Python3 bulunamadi. Yapilacaklar:
  1) Python 3.11+ kurun (ornek: https://www.python.org/downloads/ veya apt/brew)
  2) veya: export GHOST_MYSHIT_PYTHON=/tam/yol/python3
     (eski: GHOST_ATTEND_PYTHON de calisir)
  3) Docker: docker compose up --build
EOF
    exit 1
  fi
  echo "Bulundu: $SYS_PY"
  step "python3 -m venv .venv"
  "$SYS_PY" -m venv "${ROOT}/.venv"
  if [[ ! -x "$VENV_PY" ]]; then
    echo "[!] .venv olusturulamadi." >&2
    exit 1
  fi
fi

PY="$VENV_PY"
step "Python (venv): $PY"

if [[ "$SKIP_INSTALL" == false ]]; then
  [[ "$FORCE_INSTALL" == true ]] && step "ForceInstall: reinstalling all packages"
  # Tek kaynak: pyproject.toml (eski requirements.txt langchain sürümünü düşürmez)
  step "pip install -e .  (pyproject.toml)"
  "$PY" -m pip install --upgrade pip setuptools wheel
  if [[ "$FORCE_INSTALL" == true ]]; then
    "$PY" -m pip install --force-reinstall -e "${ROOT}"
  else
    "$PY" -m pip install -e "${ROOT}"
  fi
  step "playwright install chromium"
  "$PY" -m playwright install chromium
  step "Verify core imports"
  (cd "$ROOT" && "$PY" -c "from app.agent.task_agent import build_compiled_graph") || {
    echo "[!] import task_agent failed. Remove .venv and run again, or: ./Run.sh --force-install" >&2
    exit 1
  }
fi

if [[ "$INSTALL_ONLY" == true ]]; then
  echo ""
  echo "Kurulum bitti. Bot icin: ./Run.sh --skip-install"
  exit 0
fi

if [[ ! -f "${ROOT}/.env" ]]; then
  if [[ ! -f "${ROOT}/.env.example" ]]; then
    echo "[!] .env yok ve .env.example bulunamadi." >&2
    exit 1
  fi
  cp "${ROOT}/.env.example" "${ROOT}/.env"
  echo ""
  echo ".env olusturuldu (.env.example kopyasi). TELEGRAM_BOT_TOKEN ve GOOGLE_API_KEY duzenleyin."
  echo "  nano ${ROOT}/.env   veya   xdg-open ${ROOT}/.env"
  echo ""
  if [[ "$NON_INTERACTIVE" == false ]]; then
    read -r -p "Duzenledikten sonra Enter (cikis: q): " r
    [[ "$r" == "q" ]] && exit 1
  fi
fi

step "Telegram botu baslatiliyor (Ctrl+C ile durdurun)"
export PLAYWRIGHT_HEADLESS="${PLAYWRIGHT_HEADLESS:-false}"
exec "$PY" -m app.main
