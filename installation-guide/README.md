# Inštalácia servera – Náklady zákaziek

Kompletný postup od čistého počítača po bežiacu aplikáciu, ktorú používajú klient aj pracovníci z mobilov. Rovnaký postup neskôr poslúži aj na presun do cloudu.

> **Používate Claude Code?** Stačí mu povedať: *„Nainštaluj server podľa installation-guide.“* Presný postup pre agenta je v [CLAUDE.md](CLAUDE.md). Tento súbor je pre človeka.

---

## 0. Čo budete mať na konci a ktorú cestu zvoliť

Aplikácia beží v **Dockeri** ako tri kontajnery: `db` (PostgreSQL databáza), `app` (aplikácia s webom) a `scheduler` (denné spracovanie inboxu o 20:00). Dáta sú v Docker zväzkoch, takže reštart ani aktualizácia ich nezmažú.

| Cesta | Kde beží | Kto sa pripojí | Kedy ju zvoliť |
| --- | --- | --- | --- |
| **A – Lokálna sieť** | váš počítač | počítače a mobily v rovnakej Wi-Fi | skúšobná prevádzka, všetci sú v kancelárii |
| **B – Počítač + Cloudflare Tunnel** | váš počítač | ktokoľvek s prihlásením, cez internet a HTTPS | pracovníci zadávajú hodiny zo stavby; neodporúčame bez HTTPS |
| **C – Cloud server** | VPS v cloude (napr. Ubuntu 24.04) | ktokoľvek, cez vlastnú doménu a HTTPS | trvalá prevádzka, aj keď je váš počítač vypnutý |

Odporúčanie: **začnite cestou A alebo B** na svojom počítači. Keď je aplikácia overená, presuňte ju do cloudu (kapitola 9). Presun je záloha → obnova a trvá asi 30 minút.

> **Pozor pri vlastnom počítači:** keď je počítač vypnutý alebo v režime spánku, aplikácia nebeží. Pracovníci vtedy nezadajú hodiny a o 20:00 sa nespracuje inbox. Na trvalú prevádzku je vhodný cloud alebo malý počítač, ktorý stále beží.

**Odhad času:** inštalácia nástrojov 15–30 min, prvé spustenie 5–10 min (zostavenie obrazu), Google integrácia 15 min, Cloudflare Tunnel 15 min.

---

## 1. Požiadavky

| Položka | Minimum | Odporúčané |
| --- | --- | --- |
| Procesor | 2 jadrá, 64-bit (x86_64 alebo ARM, aj Apple M1–M4) | 4 jadrá |
| Pamäť | 4 GB RAM (Docker si vezme ~1,5 GB) | 8 GB a viac |
| Disk | 10 GB voľného miesta | SSD, 20 GB a viac (doklady a zálohy pribúdajú) |
| Systém | Windows 10 22H2 / 11, macOS 13+, Ubuntu 22.04 / 24.04 | — |
| Internet | áno (eKasa, Claude API, Google) | — |

Účty, ktoré budete potrebovať (stačí ich mať pripravené, nastavia sa neskôr):
- **GitHub**: prístup k repozitáru s aplikáciou.
- **Anthropic (Claude API)**: kľúč na čítanie bločkov a faktúr. Voliteľné, bez neho sa údaje dokladov zadávajú ručne.
- **Google (bežný Gmail)**: Drive inbox a e-mailové prílohy. Voliteľné.
- **Cloudflare**: len pre cestu B; bezplatný účet a doména spravovaná v Cloudflare.

---

## 2. Inštalácia nástrojov (Docker + Git)

Vyberte svoj systém.

### 2a. Windows 10 / 11

1. Otvorte **PowerShell ako správca** (Štart → napíšte „PowerShell“ → pravý klik → Spustiť ako správca) a nainštalujte WSL2:
   ```powershell
   wsl --install
   ```
   Po dokončení **reštartujte počítač**.
2. Nainštalujte Docker Desktop a Git:
   ```powershell
   winget install -e --id Docker.DockerDesktop
   ```
   ```powershell
   winget install -e --id Git.Git
   ```
   Ak `winget` nefunguje, stiahnite ich ručne: <https://www.docker.com/products/docker-desktop/> a <https://git-scm.com/download/win>.
3. Spustite **Docker Desktop**, prijmite podmienky a v **Settings** nastavte:
   - *General* → zapnuté **Use the WSL 2 based engine** a **Start Docker Desktop when you sign in to your computer**,
   - *Resources* → aspoň 4 GB pamäte (ak sa dá nastaviť).
4. Overte v novom okne PowerShellu:
   ```powershell
   docker --version
   ```
   ```powershell
   docker compose version
   ```
   ```powershell
   docker run --rm hello-world
   ```
   Posledný príkaz má vypísať „Hello from Docker!“.

Pomocné skripty `*.sh` z tohto návodu spúšťajte v programe **Git Bash** (nainštaloval sa s Gitom). Súbor `.env` vytvoríte aj priamo v PowerShelli (kapitola 4).

Licencia: Docker Desktop je bezplatný pre firmy do 250 zamestnancov a do 10 mil. USD ročného obratu.

### 2b. macOS

1. Nainštalujte nástroje pre vývojárov (obsahujú Git):
   ```bash
   xcode-select --install
   ```
2. Nainštalujte Docker Desktop: stiahnite ho z <https://www.docker.com/products/docker-desktop/> (Apple Silicon alebo Intel), alebo s Homebrew:
   ```bash
   brew install --cask docker
   ```
3. Spustite Docker Desktop a v *Settings → General* zapnite **Start Docker Desktop when you sign in**.
4. Overte:
   ```bash
   docker --version && docker compose version && docker run --rm hello-world
   ```

### 2c. Ubuntu / Debian (aj server v cloude)

Najprv stiahnite repozitár (kapitola 3), potom spustite pripravený skript. Nainštaluje Docker Engine, Compose a Git z oficiálneho repozitára Dockeru a zapne automatický štart:

```bash
sudo ./installation-guide/scripts/install-docker-ubuntu.sh
```

Potom sa **odhláste a prihláste** (alebo spustite `newgrp docker`), aby ste mohli používať `docker` bez `sudo`. Overte:

```bash
docker run --rm hello-world
```

Ak ešte nemáte Git na stiahnutie repozitára: `sudo apt-get update && sudo apt-get install -y git`.

---

## 3. Stiahnutie aplikácie

Zvoľte priečinok, kde bude aplikácia natrvalo, napríklad `C:\naklady` na Windows, `~/naklady` na macOS a Linuxe alebo `/opt/naklady` na serveri.

```bash
git clone https://github.com/3perko/New-test-repository-100eur.git naklady
```

```bash
cd naklady
```

Aplikácia je zatiaľ na vetve `claude/trusting-babbage-61jjql`. Kým sa nezlúči do hlavnej vetvy, prepnite sa na ňu:

```bash
git checkout claude/trusting-babbage-61jjql
```

Repozitár je súkromný, preto Git pri klonovaní vypýta prihlásenie. Na Windows sa otvorí okno GitHubu. Na Linuxe použite **Personal access token** namiesto hesla (GitHub → Settings → Developer settings → Personal access tokens), alebo nástroj `gh auth login`.

---

## 4. Konfigurácia (súbor `.env`)

Všetky nastavenia servera sú v súbore `.env` v koreni priečinka. Skript ho vytvorí z `.env.example` a vygeneruje náhodné tajné kľúče a heslá.

**Linux, macOS, Git Bash:**

```bash
./installation-guide/scripts/setup-env.sh
```

**Windows PowerShell:**

```powershell
powershell -ExecutionPolicy Bypass -File .\installation-guide\scripts\setup-env.ps1
```

Skript sa spýta na e-mail a meno administrátora. Ak heslo nezadáte (`--admin-password`, v PowerShelli `-AdminPassword`), vygeneruje ho a vypíše: **zapíšte si ho**. Existujúci `.env` skript nikdy neprepíše.

Čo je v `.env` (upravíte v ľubovoľnom textovom editore):

| Premenná | Význam | Kedy meniť |
| --- | --- | --- |
| `SECRET_KEY` | podpisovanie prihlásení | nastaví skript; nikomu ho neukazujte |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_NAME` | prvý administrátor; vytvorí sa len pri úplne prvom štarte | pred prvým štartom |
| `POSTGRES_PASSWORD` | heslo databázy | nastaví skript; po prvom štarte už nemeňte |
| `APP_PORT` | port na počítači (`8000`) | ak je 8000 obsadený; v cloude `127.0.0.1:8000` |
| `APP_BASE_URL` | adresa, na ktorej je aplikácia dostupná | pri ceste B a C na `https://vasa-domena` |
| `COOKIE_SECURE` | `true` pri HTTPS | pri ceste B a C |
| `ANTHROPIC_API_KEY` | Claude API (kapitola 7.1) | voliteľné |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google Drive + Gmail (kapitola 7.2) | voliteľné |
| `DOMAIN` | doména pre HTTPS v cloude (cesta C) | cesta C |
| `TUNNEL_TOKEN` | token Cloudflare Tunnelu (cesta B) | cesta B |

Súbor `.env` obsahuje tajné údaje. **Nikdy ho nedávajte do Gitu** (je v `.gitignore`) a neposielajte ho e-mailom.

---

## 5. Spustenie a overenie

```bash
docker compose up -d --build
```

Prvé spustenie trvá 5–10 minút, pretože Docker stiahne a zostaví obrazy. Ďalšie štarty trvajú sekundy. Potom spustite kontrolu (Windows: v Git Bash):

```bash
./installation-guide/scripts/check-install.sh --login VAS@EMAIL.sk VASE-HESLO
```

Na konci má byť **`VÝSLEDOK: OK`**. Upozornenia (POZOR) na chýbajúce Claude alebo Google nastavenia sú v poriadku, kým ich nenastavíte.

Otvorte prehliadač na **http://localhost:8000** a prihláste sa.

**Prvé kroky v aplikácii:** založte firmu (*Číselníky → Firmy*), zákazky, pracovníkov so sadzbami, vozidlá a používateľov pre pracovníkov. Podrobne je to v [hlavnom README](../README.md#3-prvé-kroky-v-aplikácii). Ak si chcete aplikáciu najprv vyskúšať na ukážkových dátach (vytvoria sa samostatné firmy „Demo …“):

```bash
docker compose exec app python -m app.cli seed-demo
```

Užitočné príkazy:

| Čo chcete | Príkaz |
| --- | --- |
| stav kontajnerov | `docker compose ps` |
| logy aplikácie | `docker compose logs -f app` |
| reštart | `docker compose restart` |
| zastaviť (dáta ostanú) | `docker compose stop` |
| znova spustiť | `docker compose up -d` |
| nové heslo / nový admin | `docker compose exec app python -m app.cli create-admin --email ja@firma.sk --password NoveHeslo123` |
| spracovať inbox hneď | `docker compose exec app python -m app.cli run-inbox` |

> ⚠️ **Nikdy nespúšťajte `docker compose down -v`.** Prepínač `-v` natrvalo zmaže databázu aj všetky doklady.

---

## 6. Prístup z mobilov a iných počítačov

### 6a. Cesta A – v rovnakej Wi-Fi sieti

1. Zistite IP adresu počítača so serverom:
   - Windows: `ipconfig` → „IPv4 Address“, napr. `192.168.1.25`
   - macOS: `ipconfig getifaddr en0`
   - Linux: `hostname -I`
2. Na Windows povoľte port vo firewalle (PowerShell ako správca):
   ```powershell
   New-NetFirewallRule -DisplayName "Naklady zakaziek 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
   ```
   Wi-Fi sieť musí byť vo Windows nastavená ako **Súkromná** (Private).
3. Na mobile otvorte `http://192.168.1.25:8000` a pridajte si stránku na plochu (Safari: Zdieľať → Pridať na plochu; Chrome: ⋮ → Pridať na plochu).
4. V routeri nastavte pre server **rezervovanú (statickú) IP adresu**, aby sa adresa nemenila.

Spojenie v lokálnej sieti nie je šifrované (HTTP). Mimo kancelárie ho nepoužívajte; na to slúži cesta B.

### 6b. Cesta B – z internetu cez Cloudflare Tunnel (odporúčané pre vlastný počítač)

Tunel vytvorí bezpečné HTTPS spojenie z internetu k vášmu počítaču. Na routeri netreba otvárať porty a funguje aj pri meniacej sa IP adrese.

1. Doménu (napr. `firma.sk`) majte v Cloudflare (bezplatný plán stačí; pri pridaní domény Cloudflare ukáže, ako zmeniť DNS servery u registrátora).
2. V Cloudflare otvorte **Zero Trust → Networks → Tunnels → Create a tunnel → Cloudflared**, zadajte názov (napr. `naklady`) a skopírujte **token** (dlhý reťazec za `--token`).
3. V záložke **Public Hostname** pridajte:
   - Subdomain: `naklady`, Domain: `firma.sk`
   - Service: **HTTP**, URL: **`app:8000`**
4. Do `.env` doplňte:
   ```
   TUNNEL_TOKEN=<token z kroku 2>
   APP_BASE_URL=https://naklady.firma.sk
   COOKIE_SECURE=true
   APP_PORT=127.0.0.1:8000
   ```
   `APP_PORT=127.0.0.1:8000` zatvorí nešifrovaný port pre lokálnu sieť; aplikácia bude dostupná len cez HTTPS (a lokálne na `http://localhost:8000`). Ak chcete ponechať aj prístup cez Wi-Fi podľa cesty A, nechajte `APP_PORT=8000`.
5. Spustite aplikáciu aj s tunelom:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.tunnel.yml up -d --build
   ```
6. Overte:
   ```bash
   ./installation-guide/scripts/check-install.sh --url https://naklady.firma.sk
   ```
   Potom otvorte `https://naklady.firma.sk` aj z mobilu na mobilných dátach.

Od tejto chvíle spúšťajte a aktualizujte aplikáciu vždy s oboma súbormi (`-f docker-compose.yml -f docker-compose.tunnel.yml`).

*Alternatíva bez domény:* [Tailscale](https://tailscale.com) vytvorí súkromnú sieť medzi serverom a mobilmi. Aplikácia potom nie je verejná, ale každý pracovník si musí nainštalovať aplikáciu Tailscale.

---

## 7. Integrácie

Po každej zmene `.env` reštartujte aplikáciu: `docker compose up -d` (pri ceste B s oboma `-f` súbormi). Stav integrácií vidíte v aplikácii v *Nastavenia → Integrácie*.

### 7.1 Claude API (čítanie bločkov a faktúr)
1. Na <https://platform.claude.com> si vytvorte účet, nastavte platobnú metódu a v *API Keys* vytvorte kľúč.
2. Do `.env` vložte `ANTHROPIC_API_KEY=sk-ant-...` a reštartujte aplikáciu.

Bločky sa najprv čítajú z eKasy podľa QR kódu (zadarmo) a Claude sa volá, len keď eKasa nepomôže. Faktúry číta vždy Claude.

### 7.2 Google Drive + Gmail (bežný Gmail účet)
1. <https://console.cloud.google.com> → vytvorte projekt (napr. „Naklady zakaziek“).
2. *APIs & Services → Library*: zapnite **Google Drive API** a **Gmail API**.
3. *APIs & Services → OAuth consent screen*: typ **External**, vyplňte názov a e-mail a v *Test users* pridajte svoj Gmail.
4. *APIs & Services → Credentials → Create credentials → OAuth client ID*:
   - typ **Web application**,
   - *Authorized redirect URIs*: `APP_BASE_URL` + `/api/integrations/google/callback`, napr.
     `http://localhost:8000/api/integrations/google/callback` (cesta A, pripájate z počítača so serverom) alebo
     `https://naklady.firma.sk/api/integrations/google/callback` (cesty B a C).
5. Client ID a Client secret vložte do `.env` (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`) a reštartujte aplikáciu.
6. V aplikácii otvorte *Nastavenia → Integrácie → Pripojiť Google účet* a povoľte prístup.
7. V Google Drive vytvorte pre každú firmu priečinky **na spracovanie**, **spracované** a **banka**. ID priečinka (časť adresy za `/folders/`) a e-mailové tagy (napr. `firma1-faktury`) zadajte v *Číselníky → Firmy*.

> **Dôležité:** kým je aplikácia v Google v stave **Testing**, pripojenie po 7 dňoch vyprší. Po overení, že všetko funguje, kliknite v *OAuth consent screen* na **Publish app** (stav „In production“). Pri vlastnom použití Google zobrazí varovanie „neoverená aplikácia“; potvrdíte ho cez *Rozšírené → Pokračovať*.

Google nepovoľuje presmerovanie na IP adresy (`http://192.168…`). Pri ceste A preto Google pripájajte v prehliadači priamo na serveri cez `http://localhost:8000`.

### 7.3 eKasa
Netreba nič nastavovať. Test nájdete v *Nastavenia → Integrácie* (zadáte ID bločku `O-…`).

---

## 8. Bežná prevádzka

### Automatický štart
- **Windows / macOS:** Docker Desktop so zapnutým „Start when you sign in“. Kontajnery majú `restart: unless-stopped`, takže sa spustia samy, keď sa Docker spustí. Počítač musí byť prihlásený a **nesmie zaspať**:
  - Windows: *Nastavenia → Systém → Napájanie → Režim spánku: Nikdy* (pri napájaní zo siete),
  - macOS: *Nastavenia → Batéria / Úspora energie → Zabrániť automatickému spánku*.
- **Linux:** Docker sa spúšťa so systémom (zapol ho inštalačný skript).

### Zálohy (dôležité)
Záloha databázy a dokladov sa uloží do priečinka `backups/` a záznamy staršie ako 30 dní sa mažú:

```bash
./deploy/backup.sh
```

Zálohujte automaticky denne:
- **Linux / macOS** (`crontab -e`, uprav cestu):
  ```
  15 2 * * * /opt/naklady/deploy/backup.sh >> /opt/naklady/backups/backup.log 2>&1
  ```
- **Windows** (PowerShell, cesta `C:\naklady`; úloha beží, keď ste prihlásený a Docker Desktop je spustený):
  ```powershell
  $a = New-ScheduledTaskAction -Execute "C:\Program Files\Git\bin\bash.exe" -Argument "-lc 'cd /c/naklady && ./deploy/backup.sh >> backups/backup.log 2>&1'"
  Register-ScheduledTask -TaskName "Naklady zaloha" -Action $a -Trigger (New-ScheduledTaskTrigger -Daily -At "02:15")
  ```

Zálohu majte **aj mimo počítača**, napríklad nech sa priečinok `backups` synchronizuje cez Google Drive pre počítač, alebo ho pravidelne kopírujte na externý disk. Záloha na tom istom disku vás pri poruche disku nezachráni.

Obnova zo zálohy (prepíše aktuálne dáta, preto si vyžiada potvrdenie):

```bash
./installation-guide/scripts/restore.sh backups/db-RRRRMMDD-HHMM.dump backups/files-RRRRMMDD-HHMM.tar.gz
```

### Aktualizácia na novú verziu
Skript urobí zálohu, stiahne novú verziu, prebuduje aplikáciu (databázové migrácie sa spustia samy) a overí ju:

```bash
./installation-guide/scripts/update.sh
```

Pri ceste B pridajte tunel: `./installation-guide/scripts/update.sh -f docker-compose.tunnel.yml`; pri ceste C: `… -f docker-compose.prod.yml`.

---

## 9. Presun do cloudu (cesta C)

1. **Server:** u poskytovateľa VPS (napr. Hetzner, DigitalOcean, Contabo, WebSupport) si vytvorte server **Ubuntu 24.04 LTS**, 2 vCPU, 4 GB RAM, 40 GB disk. Prihláste sa cez SSH.
2. **DNS:** u správcu domény vytvorte záznam `A` pre `naklady.firma.sk` → IP adresa servera.
3. **Firewall** (otvorené len SSH, HTTP a HTTPS):
   ```bash
   sudo ufw allow OpenSSH && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw --force enable
   ```
4. **Nástroje a aplikácia:**
   ```bash
   sudo apt-get update && sudo apt-get install -y git
   ```
   ```bash
   sudo git clone https://github.com/3perko/New-test-repository-100eur.git /opt/naklady && sudo chown -R "$USER" /opt/naklady && cd /opt/naklady && git checkout claude/trusting-babbage-61jjql
   ```
   ```bash
   sudo ./installation-guide/scripts/install-docker-ubuntu.sh && newgrp docker
   ```
5. **Konfigurácia:**
   ```bash
   ./installation-guide/scripts/setup-env.sh --admin-email ja@firma.sk --base-url https://naklady.firma.sk --port 127.0.0.1:8000 --domain naklady.firma.sk
   ```
   Ostatné hodnoty (Claude, Google) prepíšte z `.env` na pôvodnom počítači. **`SECRET_KEY` a `POSTGRES_PASSWORD` nechajte nové.**
6. **Prenos dát:** na pôvodnom počítači spustite `./deploy/backup.sh` a dva najnovšie súbory z `backups/` skopírujte na server, napr.:
   ```bash
   scp backups/db-*.dump backups/files-*.tar.gz pouzivatel@IP-servera:/opt/naklady/backups/
   ```
   Na serveri zostavte aplikáciu a obnovte dáta:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml build
   ```
   ```bash
   ./installation-guide/scripts/restore.sh backups/db-RRRRMMDD-HHMM.dump backups/files-RRRRMMDD-HHMM.tar.gz
   ```
7. **Spustenie s HTTPS** (Caddy vybaví certifikát Let's Encrypt automaticky):
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
   ```
8. **Overenie:**
   ```bash
   ./installation-guide/scripts/check-install.sh --url https://naklady.firma.sk
   ```
9. V Google Cloud Console pridajte nový redirect URI (`https://naklady.firma.sk/api/integrations/google/callback`) a v aplikácii znova pripojte Google účet.
10. Nastavte denné zálohy (kapitola 8) a pôvodný počítač zastavte (`docker compose stop`), aby nebežali dve verzie naraz.

Aj v cloude môžete namiesto Caddy použiť Cloudflare Tunnel (kapitola 6b). Vtedy netreba otvárať porty 80 a 443.

---

## 10. Bezpečnosť – kontrolný zoznam

- [ ] Heslo administrátora je silné a po prvom prihlásení ste ho zmenili, ak bolo vygenerované.
- [ ] Každý pracovník má vlastný účet s rolou **Pracovník**; účty sa nezdieľajú.
- [ ] Mimo lokálnej siete je aplikácia dostupná **len cez HTTPS** (cesta B alebo C), nikdy cez otvorený port 8000 na routeri.
- [ ] `.env` nie je v Gite ani v e-mailoch; `COOKIE_SECURE=true` pri HTTPS.
- [ ] Denné zálohy bežia a kópia je mimo servera; obnovu ste aspoň raz vyskúšali.
- [ ] Systém a Docker sa aktualizujú (Windows Update / `sudo apt upgrade`), aplikácia cez `update.sh`.
- [ ] Na serveri v cloude je zapnutý firewall (`ufw`) a prihlásenie SSH kľúčom.

---

## 11. Riešenie problémov

| Príznak | Príčina | Riešenie |
| --- | --- | --- |
| `docker: command not found` / „Cannot connect to the Docker daemon“ | Docker nie je nainštalovaný alebo nebeží | spustite Docker Desktop; Linux: `sudo systemctl start docker` |
| `permission denied … docker.sock` (Linux) | používateľ nie je v skupine docker | odhláste a prihláste sa, alebo `newgrp docker` |
| `port is already allocated` / `address already in use` | port 8000 používa iný program | v `.env` nastavte `APP_PORT=8080` a otvorte `http://localhost:8080` |
| `429 Too Many Requests` pri sťahovaní obrazov | limit Docker Hubu | počkajte 1 hodinu, alebo `docker login` (bezplatný účet má vyšší limit) |
| zostavenie spadne s `Killed` / `exit code 137` | málo pamäte | v Docker Desktop → Resources zvýšte pamäť na 4 GB a viac |
| prihlásenie nefunguje, „Nesprávny e-mail alebo heslo“ | admin z `.env` vzniká len pri prvom štarte | `docker compose exec app python -m app.cli create-admin --email … --password …` |
| po prihlásení ma to hneď odhlási (HTTP) | `COOKIE_SECURE=true` bez HTTPS | pri `http://` nastavte `COOKIE_SECURE=false` |
| Google: `redirect_uri_mismatch` | URI v Google Console ≠ `APP_BASE_URL` + `/api/integrations/google/callback` | opravte presne vrátane `http`/`https` a portu |
| Google prestal fungovať po týždni | aplikácia v stave Testing | *OAuth consent screen → Publish app* a pripojte znova |
| mobil sa nepripojí (cesta A) | firewall alebo iná sieť | pravidlo firewallu z kap. 6a, sieť „Súkromná“, rovnaká Wi-Fi |
| skript `.sh` na Windows: `$'\r': command not found` | Windows konce riadkov | `git config core.autocrlf false`, potom `git checkout -- .` (repozitár má `.gitattributes`) |
| `app` sa stále reštartuje | chyba v konfigurácii alebo DB | `docker compose logs app --tail 100` |
| `check-install.sh` hlási CHYBA | konkrétny riadok hovorí čo | opravte podľa textu, spustite znova |

Ak si neviete rady, pošlite výstup `./installation-guide/scripts/check-install.sh` a `docker compose logs app --tail 100`, **nikdy však nie obsah `.env`**.

---

## Obsah priečinka

| Súbor | Účel |
| --- | --- |
| `README.md` | tento návod (pre človeka) |
| `CLAUDE.md` | presný postup pre Claude Code (agent) |
| `scripts/setup-env.sh`, `scripts/setup-env.ps1` | vytvorenie `.env` s vygenerovanými tajomstvami |
| `scripts/install-docker-ubuntu.sh` | Docker + Compose + Git na Ubuntu/Debian |
| `scripts/check-install.sh` | overenie inštalácie (návratový kód 0 = OK) |
| `scripts/update.sh` | záloha → nová verzia → reštart → kontrola |
| `scripts/restore.sh` | obnova zo zálohy (aj pri presune do cloudu) |
| `../deploy/backup.sh` | záloha databázy a dokladov |
| `../docker-compose.tunnel.yml` | Cloudflare Tunnel (cesta B) |
| `../docker-compose.prod.yml` | Caddy s HTTPS (cesta C) |
