#!/usr/bin/env bash
# Overí, že inštalácia funguje. Každý riadok je OK / CHYBA / POZOR; na konci súhrn.
# Návratový kód 0 = všetko podstatné je v poriadku (vhodné pre agenta aj CI).
# Použitie: ./installation-guide/scripts/check-install.sh [--url http://localhost:8000] [--login email heslo]
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

URL="" LOGIN_EMAIL="" LOGIN_PWD=""
while [ $# -gt 0 ]; do
  case "$1" in
    --url) URL="$2"; shift 2 ;;
    --login) LOGIN_EMAIL="$2"; LOGIN_PWD="$3"; shift 3 ;;
    *) echo "Neznámy parameter: $1" >&2; exit 2 ;;
  esac
done

FAIL=0 WARN=0
ok()   { printf '  \033[32mOK\033[0m     %s\n' "$1"; }
bad()  { printf '  \033[31mCHYBA\033[0m  %s\n' "$1"; FAIL=$((FAIL + 1)); }
warn() { printf '  \033[33mPOZOR\033[0m  %s\n' "$1"; WARN=$((WARN + 1)); }
env_get() { [ -f .env ] && grep -E "^$1=" .env | tail -1 | cut -d= -f2- | tr -d '\r'; }

echo "== Nástroje"
if command -v docker >/dev/null 2>&1; then ok "docker $(docker --version | awk '{print $3}' | tr -d ,)"; else bad "docker nie je nainštalovaný"; fi
if docker compose version >/dev/null 2>&1; then ok "docker compose $(docker compose version --short)"; else bad "docker compose plugin chýba"; fi
if docker info >/dev/null 2>&1; then ok "Docker démon beží"; else bad "Docker démon nebeží (spustite Docker Desktop / sudo systemctl start docker)"; fi
command -v git >/dev/null 2>&1 && ok "git" || warn "git chýba (potrebný na aktualizácie)"

echo "== Konfigurácia (.env)"
if [ -f .env ]; then
  ok ".env existuje"
  sk="$(env_get SECRET_KEY)"
  if [ -z "$sk" ] || [ "$sk" = "zmente-ma-na-nahodny-dlhy-retazec" ] || [ "${#sk}" -lt 32 ]; then bad "SECRET_KEY nie je nastavený (spustite setup-env)"; else ok "SECRET_KEY nastavený"; fi
  pg="$(env_get POSTGRES_PASSWORD)"
  if [ -z "$pg" ] || [ "$pg" = "zmente-heslo-db" ]; then bad "POSTGRES_PASSWORD má predvolenú hodnotu"; else ok "POSTGRES_PASSWORD nastavené"; fi
  [ "$(env_get ADMIN_PASSWORD)" = "zmente-heslo" ] && bad "ADMIN_PASSWORD má predvolenú hodnotu" || ok "ADMIN_PASSWORD zmenené"
  [ -n "$(env_get ANTHROPIC_API_KEY)" ] && ok "Claude API kľúč nastavený" || warn "ANTHROPIC_API_KEY prázdny – doklady sa budú dopĺňať ručne"
  if [ -n "$(env_get GOOGLE_CLIENT_ID)" ] && [ -n "$(env_get GOOGLE_CLIENT_SECRET)" ]; then ok "Google OAuth klient nastavený"; else warn "Google OAuth nenastavený – Drive/Gmail nebude fungovať (voliteľné)"; fi
  base="$(env_get APP_BASE_URL)"
  case "$base" in https://*) [ "$(env_get COOKIE_SECURE)" = "true" ] && ok "HTTPS + COOKIE_SECURE=true" || warn "APP_BASE_URL je https, ale COOKIE_SECURE nie je true" ;; esac
else
  bad ".env chýba – spustite installation-guide/scripts/setup-env.sh (Windows: setup-env.ps1)"
fi

echo "== Kontajnery"
if docker info >/dev/null 2>&1; then
  for svc in db app scheduler; do
    state="$(docker compose ps --format '{{.Service}} {{.State}}' 2>/dev/null | awk -v s="$svc" '$1==s {print $2}')"
    if [ "$state" = "running" ]; then ok "$svc beží"; else bad "$svc nebeží (stav: ${state:-neexistuje}) – docker compose up -d --build"; fi
  done
  restarts="$(docker compose ps --format '{{.Service}} {{.Status}}' 2>/dev/null | grep -i restarting || true)"
  [ -n "$restarts" ] && bad "kontajner sa reštartuje dookola: $restarts (pozri docker compose logs)"
fi

echo "== Aplikácia"
if [ -z "$URL" ]; then
  port="$(env_get APP_PORT)"; port="${port:-8000}"; port="${port##*:}"
  URL="http://localhost:$port"
fi
if command -v curl >/dev/null 2>&1; then
  health="$(curl -fsS --max-time 5 "$URL/api/health" 2>/dev/null || true)"
  if echo "$health" | grep -q '"ok":true'; then ok "API odpovedá na $URL/api/health"; else bad "API neodpovedá na $URL/api/health"; fi
  if curl -fsS --max-time 5 "$URL/" 2>/dev/null | grep -q "<title>Náklady zákaziek</title>"; then ok "webové rozhranie sa načíta"; else bad "webové rozhranie sa nenačíta na $URL/"; fi
  if [ -n "$LOGIN_EMAIL" ]; then
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 -H 'X-Requested-With: app' -H 'Content-Type: application/json' \
      -d "{\"email\":\"$LOGIN_EMAIL\",\"password\":\"$LOGIN_PWD\"}" "$URL/api/auth/login")"
    [ "$code" = "200" ] && ok "prihlásenie $LOGIN_EMAIL funguje" || bad "prihlásenie $LOGIN_EMAIL zlyhalo (HTTP $code)"
  fi
else
  warn "curl chýba – webovú časť neoverujem"
fi

echo "== Disk"
free_kb="$(df -Pk . | awk 'NR==2 {print $4}')"
if [ -n "$free_kb" ] && [ "$free_kb" -lt 5242880 ]; then warn "menej ako 5 GB voľného miesta"; else ok "voľné miesto: $((free_kb / 1048576)) GB"; fi
[ -d backups ] && ok "priečinok backups existuje ($(ls backups 2>/dev/null | wc -l | tr -d ' ') súborov)" || warn "zatiaľ žiadna záloha (deploy/backup.sh)"

echo
if [ "$FAIL" -eq 0 ]; then
  printf '\033[32mVÝSLEDOK: OK\033[0m (%s upozornení)\n' "$WARN"; exit 0
else
  printf '\033[31mVÝSLEDOK: %s chýb, %s upozornení\033[0m\n' "$FAIL" "$WARN"; exit 1
fi
