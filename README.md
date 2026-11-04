# Náklady zákaziek

Webová aplikácia na evidenciu nákladov, výnosov a ziskovosti zákaziek pre viac firiem (s.r.o.).
Úplný popis produktu je v **[docs/master-prompt.md](docs/master-prompt.md)**. Je to zdroj pravdy a nové funkcie sa dopĺňajú tam.

- **Backend:** FastAPI (Python 3.12), PostgreSQL 16, SQLAlchemy 2 + Alembic, plánovač APScheduler
- **Frontend:** React 18 + TypeScript, Vite, TanStack Table + Query, Tailwind CSS (svetlý aj tmavý režim, mobile-first)
- **Nasadenie:** Docker Compose na Ubuntu serveri, HTTPS cez Caddy

Návod na overenie funkcií krok za krokom je v **[docs/navod-overenie.md](docs/navod-overenie.md)**.

---

## 1. Rýchle spustenie (Docker)

Potrebujete Docker s Compose pluginom (Ubuntu: `sudo apt install docker.io docker-compose-v2`).

```bash
git clone <adresa-repozitára> naklady && cd naklady
```

```bash
cp .env.example .env
```

V súbore `.env` nastavte aspoň `SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` a `POSTGRES_PASSWORD`. Potom spustite:

```bash
docker compose up -d --build
```

Aplikácia beží na **http://localhost:8000**. Prihláste sa e-mailom a heslom z `.env`.
Pri prvom štarte sa automaticky vytvorí databázová schéma aj prvý administrátor.

Voliteľné demo dáta (2 firmy, zákazky, pracovníci so sadzbami, vozidlá, hodiny a jazdy) na vyskúšanie:

```bash
docker compose exec app python -m app.cli seed-demo
```

Demo dáta sú v samostatných firmách „Demo Stavby s.r.o.“ a „Demo Servis s.r.o.“. Ak ich nechcete, nespúšťajte tento príkaz, alebo neskôr tieto firmy deaktivujte.

### Užitočné príkazy

```bash
docker compose logs -f app
```

```bash
docker compose exec app python -m app.cli create-admin --email novy@firma.sk --password NoveHeslo123
```

```bash
docker compose exec app python -m app.cli run-inbox
```

```bash
docker compose pull && docker compose up -d --build
```

## 2. Produkčné nasadenie s HTTPS (Ubuntu + doména)

1. DNS záznam domény (napr. `naklady.firma.sk`) nasmerujte na IP servera a otvorte porty 80 a 443.
2. V `.env` nastavte:
   ```
   DOMAIN=naklady.firma.sk
   APP_BASE_URL=https://naklady.firma.sk
   COOKIE_SECURE=true
   APP_PORT=127.0.0.1:8000
   ```
3. Spustite aplikáciu spolu s Caddy (certifikát Let's Encrypt sa vybaví automaticky):
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```
4. Zálohy (databáza + uložené súbory), napríklad denne cez cron:
   ```bash
   ./deploy/backup.sh
   ```
   Obnova databázy zo zálohy:
   ```bash
   docker compose exec -T db pg_restore -U app -d naklady --clean < backups/db-RRRRMMDD-HHMM.dump
   ```

## 3. Prvé kroky v aplikácii

1. **Číselníky → Firmy:** založte firmy (IČO, IČ DPH, platiteľ DPH). Každá nová firma automaticky dostane zákazku **Réžia**.
2. Hore v hlavičke zvoľte **aktívnu firmu**. Všetko ďalej (doklady, zákazky, banka, DPH) sa týka len nej.
3. **Číselníky → Bankové účty, Číselné rady, Odberatelia, Zákazky** (vzdialenosť jedným smerom, rozpočet, typ fakturácie).
4. **Číselníky → Pracovníci** (firmy, pre ktoré pracujú) a **Sadzby pracovníkov**. Nákladová aj fakturačná sadzba môže byť default, pre firmu alebo pre zákazku, vždy s platnosťou od–do.
5. **Vozový park → Vozidlá** (sadzba €/km pri založení, ďalšie zmeny v „Sadzby €/km“), PZP, známky, servis.
6. **Nastavenia → Používatelia a roly:** pracovníkom vytvorte účty s rolou *Pracovník* a prepojte ich so záznamom pracovníka. Uvidia len Hodiny, Jazdy a svoj podklad.
7. **Nastavenia → Parametre:** prirážka k vzdialenosti (10 %), zaokrúhlenie hodín, dni na doloženie dokladu, prirážka na materiál, predstih upozornení, čas spracovania inboxu (20:00) a ďalšie.

## 4. Integrácie

### Claude API (čítanie bločkov a faktúr)
Do `.env` vložte `ANTHROPIC_API_KEY` (konzola: https://platform.claude.com). Bločky sa najprv skúsia načítať z eKasy podľa QR kódu a Claude API sa použije, len keď eKasa nepomôže. Faktúry sa čítajú cez Claude API. Bez kľúča aplikácia funguje, len údaje dokladov treba doplniť ručne.

### eKasa (Finančná správa)
Je zapnutá v predvolenom nastavení. ID dokladu (`O-…`) sa číta deterministicky z QR kódu. Test pripojenia nájdete v *Nastavenia → Integrácie*.

### Google Drive + Gmail (bežný Gmail účet)
1. V [Google Cloud Console](https://console.cloud.google.com/) vytvorte projekt a zapnite **Google Drive API** a **Gmail API**.
2. *OAuth consent screen*: typ **External**, pridajte svoj Gmail ako testovacieho používateľa.
   Upozornenie: kým je aplikácia v stave „Testing“, Google platnosť pripojenia zruší po 7 dňoch. Pre trvalú prevádzku zmeňte stav na „In production“; pri vlastnom použití stačí potvrdiť varovanie „neoverená aplikácia“.
3. *Credentials → Create OAuth client ID* → **Web application**, *Authorized redirect URI*:
   `https://<vaša-doména>/api/integrations/google/callback` (lokálne `http://localhost:8000/api/integrations/google/callback`).
4. `GOOGLE_CLIENT_ID` a `GOOGLE_CLIENT_SECRET` vložte do `.env` a reštartujte (`docker compose up -d`).
5. V aplikácii otvorte *Nastavenia → Integrácie → Pripojiť Google účet*.
6. Pri každej firme (*Číselníky → Firmy*) vyplňte:
   - **ID priečinka inbox** („na spracovanie“), **ID priečinka spracované** a **ID bankového inboxu**. ID je časť URL priečinka za `/folders/`.
   - **E-mail tag pre faktúry / výpisy**, napr. `firma1-faktury` → dodávatelia posielajú na `vasmeno+firma1-faktury@gmail.com`.
7. Denne v nastavenom čase (default 20:00) plánovač stiahne prílohy z Gmailu do Drive inboxu, z Drive inboxu prevezme nové súbory, presunie ich do „spracované“ a spracuje ich. Ručne to spustíte tlačidlom **Spracovať inbox teraz**.

Paralelná prevádzka podľa master promptu: aplikácia má používať **nový, čistý Google Drive** s rovnakou štruktúrou, aby sa jej výsledky dali porovnať s vašimi existujúcimi podkladmi.

### Bankové výpisy
Výpisy nahrajte v *Financie → Banka → Importovať výpis*, alebo cez e-mail tag pre výpisy / bankový Drive inbox. Podporované formáty sú XML CAMT.053, CSV, XLSX a PDF (PDF cez Claude API). Účet sa priradí podľa IBAN. Ak IBAN nepatrí aktívnej firme, výpis sa odmietne.

### Overenie vozidla
Verejné služby (eznamka.sk, SKP, TÜV SÜD) nemajú verejné API. Aplikácia preto otvorí overovaciu stránku, skopíruje ŠPZ do schránky a výsledok zapíšete jedným klikom. Pri nezhode s evidenciou vznikne upozornenie. Nové služby sa pridávajú ako adaptér v `backend/app/services/vehicle_check.py`.

## 5. Lokálny vývoj bez Dockeru

Potrebujete PostgreSQL 16, Python 3.12+ a Node 22.

```bash
cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
```

```bash
cp ../.env.example .env   # nastavte DATABASE_URL=postgresql+psycopg://app:app@localhost:5432/naklady
```

```bash
alembic upgrade head && python -m app.cli create-admin --email admin@example.com --password admin12345
```

```bash
uvicorn app.main:app --reload --port 8000
```

V druhom termináli spustite frontend s hot reload na http://localhost:5173 (proxy na API):

```bash
cd frontend && npm install && npm run dev
```

### Testy

```bash
cd backend && createdb naklady_test && .venv/bin/pytest -q
```

```bash
cd frontend && npm run typecheck && npm run build
```

## 6. Architektúra

```
backend/app
├── models/          dátový model (core, work = hodiny/jazdy/vozidlá, docs = doklady/banka/fakturácia)
├── registry/        register polí (field registry) + univerzálny zoznamový engine a generické CRUD s audit logom
├── services/        doménové moduly: calc (sadzby, km), documents, ingest (inbox → doklad), prep (PDF/QR),
│                    ekasa, extraction (Claude API), bank + bank_parsers, billing, reports (náklady, ziskovosť,
│                    DPH, mesačná kontrola, vozový park), vehicle_check, google (Drive/Gmail), exports, jobs
├── routers/         REST API
├── scheduler.py     plánovač (denné spracovanie inboxu)
└── cli.py           create-admin, seed-demo, run-inbox
frontend/src
├── components/      DataTable (výber stĺpcov, filtre, pohľady, súčty, zoskupenie, export), vstupy (dátum, čas 24 h…)
└── pages/           stránky podľa logických celkov (Prehľady, Doklady, Práca a doprava, Vozový park, Financie…)
```

- **Nové pole v UI:** stačí ho pridať do modelu (+ migrácia `alembic revision --autogenerate`) a do registra v `backend/app/registry/entities.py`. Frontend ho automaticky ponúkne vo výbere stĺpcov, filtroch, exporte aj vo formulári.
- **Deterministika pred LLM:** QR/eKasa, duplicity, číselné rady, párovanie banky a všetky výpočty sú bez LLM. Claude API sa používa len na čítanie dokladov, ktoré eKasa nepozná, a na PDF výpisy.
- **Jedna aktívna firma:** každý záznam nesie `company_id` a API pracuje len s dátami aktívnej firmy (hlavička `X-Company-Id`).

## 7. Stav implementácie

V1 (fázy 1–6 z master promptu) je implementovaná celá. Na neskôr ostáva:
- WhatsApp (hodiny z chatov, bločky zo skupín), AI asistent nad databázou, týždenné reporty a stavebný denník,
- priame napojenie na banky cez API a na účtovníctvo, vystavovanie faktúr priamo z aplikácie,
- otvorený bod „Nákladovosť na …“ (kapitola 4 master promptu).
