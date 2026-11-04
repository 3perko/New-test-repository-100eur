#!/usr/bin/env bash
# Vytvorí súbor .env v koreni repozitára z .env.example a vygeneruje bezpečné tajné hodnoty.
# Linux / macOS / WSL. Nikdy neprepíše existujúci .env (iba s --force).
#
# Použitie (interaktívne):      ./installation-guide/scripts/setup-env.sh
# Použitie (bez otázok, agent):  ./installation-guide/scripts/setup-env.sh --admin-email ja@firma.sk \
#                                   [--admin-password HESLO] [--admin-name "Meno"] [--base-url URL] [--port 8000] \
#                                   [--anthropic-key KEY] [--google-id ID --google-secret SECRET] [--domain DOMENA] \
#                                   [--tunnel-token TOKEN] [--non-interactive] [--force]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="$ROOT/.env"
EXAMPLE="$ROOT/.env.example"

ADMIN_EMAIL="" ADMIN_PASSWORD="" ADMIN_NAME="" BASE_URL="" PORT="" ANTHROPIC="" GID="" GSECRET="" DOMAIN="" TUNNEL=""
FORCE=0 NONINTERACTIVE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --admin-email) ADMIN_EMAIL="$2"; shift 2 ;;
    --admin-password) ADMIN_PASSWORD="$2"; shift 2 ;;
    --admin-name) ADMIN_NAME="$2"; shift 2 ;;
    --base-url) BASE_URL="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --anthropic-key) ANTHROPIC="$2"; shift 2 ;;
    --google-id) GID="$2"; shift 2 ;;
    --google-secret) GSECRET="$2"; shift 2 ;;
    --domain) DOMAIN="$2"; shift 2 ;;
    --tunnel-token) TUNNEL="$2"; shift 2 ;;
    --non-interactive) NONINTERACTIVE=1; shift ;;
    --force) FORCE=1; shift ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "Neznámy parameter: $1" >&2; exit 2 ;;
  esac
done

if [ ! -f "$EXAMPLE" ]; then echo "CHYBA: chýba $EXAMPLE – spúšťate skript z klonu repozitára?" >&2; exit 1; fi
if [ -f "$ENV_FILE" ] && [ "$FORCE" -ne 1 ]; then
  echo "OK: $ENV_FILE už existuje – nič nemením (na prepísanie použite --force)."
  exit 0
fi

rand() { # $1 = number of bytes -> hex
  if command -v openssl >/dev/null 2>&1; then openssl rand -hex "$1"
  else head -c "$1" /dev/urandom | od -An -tx1 | tr -d ' \n'; fi
}

ask() { # $1 prompt, $2 default -> echo answer
  local a=""
  if [ "$NONINTERACTIVE" -eq 1 ] || [ ! -t 0 ]; then echo "$2"; return; fi
  read -r -p "$1 [$2]: " a || true
  echo "${a:-$2}"
}

[ -z "$ADMIN_EMAIL" ] && ADMIN_EMAIL="$(ask 'E-mail administrátora (prihlasovacie meno)' 'admin@example.com')"
[ -z "$ADMIN_NAME" ] && ADMIN_NAME="$(ask 'Meno administrátora' 'Administrátor')"
GENERATED_PWD=0
if [ -z "$ADMIN_PASSWORD" ]; then ADMIN_PASSWORD="$(rand 9)"; GENERATED_PWD=1; fi
if [ "${#ADMIN_PASSWORD}" -lt 8 ]; then echo "CHYBA: heslo administrátora musí mať aspoň 8 znakov." >&2; exit 1; fi
[ -z "$PORT" ] && PORT="8000"
[ -z "$BASE_URL" ] && BASE_URL="http://localhost:${PORT##*:}"

# KEY=VALUE pairs that replace lines in .env.example (portable: works with bash 3.2 on macOS)
VALS="$(mktemp)"
{
  echo "SECRET_KEY=$(rand 32)"
  echo "POSTGRES_PASSWORD=$(rand 16)"
  echo "ADMIN_EMAIL=$ADMIN_EMAIL"
  echo "ADMIN_PASSWORD=$ADMIN_PASSWORD"
  echo "ADMIN_NAME=$ADMIN_NAME"
  echo "APP_PORT=$PORT"
  echo "APP_BASE_URL=$BASE_URL"
  [ -n "$ANTHROPIC" ] && echo "ANTHROPIC_API_KEY=$ANTHROPIC"
  [ -n "$GID" ] && echo "GOOGLE_CLIENT_ID=$GID"
  [ -n "$GSECRET" ] && echo "GOOGLE_CLIENT_SECRET=$GSECRET"
  [ -n "$DOMAIN" ] && echo "DOMAIN=$DOMAIN"
  [ -n "$TUNNEL" ] && echo "TUNNEL_TOKEN=$TUNNEL"
  case "$BASE_URL" in https://*) echo "COOKIE_SECURE=true" ;; esac
} > "$VALS"

TMP="$(mktemp)"
awk 'NR == FNR { i = index($0, "="); v[substr($0, 1, i - 1)] = substr($0, i + 1); next }
     /^[A-Z_]+=/ { k = substr($0, 1, index($0, "=") - 1); if (k in v) { print k "=" v[k]; next } }
     { print }' "$VALS" "$EXAMPLE" > "$TMP"
rm -f "$VALS"
mv "$TMP" "$ENV_FILE"
chmod 600 "$ENV_FILE"

echo "OK: vytvorený $ENV_FILE"
echo "    prihlásenie:  $ADMIN_EMAIL"
if [ "$GENERATED_PWD" -eq 1 ]; then
  echo "    heslo:        $ADMIN_PASSWORD   (vygenerované – zapíšte si ho, po prihlásení ho môžete zmeniť)"
fi
echo "    adresa:       $BASE_URL"
echo "Ďalší krok: docker compose up -d --build"
