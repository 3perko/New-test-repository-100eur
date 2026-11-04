#!/usr/bin/env bash
# Inštalácia Docker Engine + Compose pluginu + git na Ubuntu / Debian (aj WSL2 Ubuntu) z oficiálneho repozitára Dockeru.
# Idempotentné: ak Docker s Compose už je, nič neinštaluje.
# Použitie: sudo ./installation-guide/scripts/install-docker-ubuntu.sh
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then echo "Spustite cez sudo: sudo $0" >&2; exit 1; fi
TARGET_USER="${SUDO_USER:-$(logname 2>/dev/null || echo root)}"

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  echo "OK: Docker už je nainštalovaný: $(docker --version) / $(docker compose version --short)"
else
  . /etc/os-release
  case "$ID" in
    ubuntu|debian) DISTRO="$ID" ;;
    *) case "${ID_LIKE:-}" in *ubuntu*) DISTRO=ubuntu ;; *debian*) DISTRO=debian ;; *)
         echo "CHYBA: nepodporovaná distribúcia ($ID). Postup: https://docs.docker.com/engine/install/" >&2; exit 1 ;; esac ;;
  esac
  CODENAME="${UBUNTU_CODENAME:-$VERSION_CODENAME}"
  echo ">> Inštalujem Docker pre $DISTRO $CODENAME"
  apt-get update
  apt-get install -y ca-certificates curl gnupg git
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/$DISTRO/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/$DISTRO $CODENAME stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

command -v git >/dev/null 2>&1 || apt-get install -y git

# Docker sa má spúšťať automaticky po štarte systému (na WSL bez systemd sa preskočí)
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  systemctl enable --now docker >/dev/null 2>&1 || true
fi

# Používateľ môže používať docker bez sudo (prejaví sa po novom prihlásení)
if [ "$TARGET_USER" != "root" ] && ! id -nG "$TARGET_USER" | grep -qw docker; then
  usermod -aG docker "$TARGET_USER"
  echo ">> Používateľ $TARGET_USER pridaný do skupiny docker – odhláste sa a prihláste znova (alebo: newgrp docker)."
fi

docker --version
docker compose version
echo "OK: Docker je pripravený."
