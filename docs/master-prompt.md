# Aplikácia na evidenciu nákladov zákaziek – master prompt

Verzia 1.1 · Nov 4, 2026 · @Miroslav Mika
(v1.0 Nov 1, 2026 + pripomienky zákazníka + požiadavky na UI; zoznam zmien je v kapitole 5)

> Tento dokument je **úplný popis aplikácie** (master prompt). Nové funkcie sa dopĺňajú sem, nie iteratívne do kódu. Podľa tohto dokumentu má byť možné celý produkt kedykoľvek znovu vygenerovať.

## 1. Súhrn rozhovoru

Hlavný záver: vytvorenie aplikácie pre klienta, ktorý spravuje viacero rôznych firiem.

**Hlavný cieľ:** na otázku „aký je aktuálny stav nákladov na zákazku X“ odpovedať okamžite a presne. Náklad zákazky = **bločky + faktúry (materiál) + hodiny × nákladová sadzba + km × sadzba vozidla**. Hodiny sú najväčšia položka, nasleduje materiál.

**Druhý cieľ (v1.1):** na otázku „koľko na zákazke X zarábame a čo môžem vyfakturovať“ odpovedať rovnako rýchlo – **ziskovosť** (výnosy − náklady) celkovo aj po zákazkách a **podklad k fakturácii**.

Rozsah:

- Prehľad všetkých nákladov
- Prehľad ziskovosti – celkovo za firmu aj na zákazku
- Podklad k fakturácii zákazníkovi a výstupy pre pracovníkov
- Evidencia hodín pracovníkov
- Evidencia jázd áut a súvisiacich nákladov
- Vozový park vrátane PZP, diaľničných známok, servisu a overenia údajov
- Evidencia bločkov a faktúr s následným priradením nákladov
- Kontrola bankových výpisov voči evidovaným dokladom
- Podklady pre účely DPH a iné
- Evidencia všetkých projektov vo firmách a ich parametrov (napr. vzdialenosť) pre následné priraďovanie nákladov, ale aj pre výpočet nákladov na cesty autom
- Aplikácia musí byť čo najviac modulárna, aby sa neskoršie zmeny v jednom module dotýkali čo najmenej iných modulov
- Google Drive a Gmail sú súčasťou od začiatku; neskôr integrácia s WhatsAppom a ďalšími službami

### Ako klient pracuje dnes

- Klient spravuje viacero firiem (samostatné s.r.o.). Každá firma má vlastné doklady, zákazky a DPH; náklady medzi firmami neprechádzajú. V rámci jednej firmy môžu faktúry vystavovať aj jej oddelené časti, napr. dve osoby, každá vo vlastnom číselnom rade.
- Evidencia faktúr a bločkov cez **Google Drive** po mesiacoch (DPH podľa mesiacov).
- Elektronické doklady (Alza, faktúry dodávateľov, parkovanie) chodia e-mailom a ručne ich nahráva na Google Drive.
- **Pracovníci** pri nákupe firemnou kartou bloček odfotia a pošlú do WhatsApp skupiny zákazky (napr. „Sikorky“). Fyzický bloček často príde neskoro (aj o 2 mesiace) a klient ho skenuje znova, čiže vznikajú aj duplicity a treba to overovať.
- **Hodiny**: každý pracovník má s klientom vlastný WhatsApp chat „Hodiny“ a denne píše meno, dátum, zákazku, od–do, počet hodín a popis práce. Klient na konci mesiaca exportuje text chatu do Clauda, ktorý to spracuje a doplňujúcimi otázkami dočistí.
- **Zákazkové skupiny** vo WhatsAppe obsahujú fotky, videá, komplikácie a vícepráce.
- Klient si vytvoril **Google formulár** (vozidlo, km, ľudia v aute, zákazka, dátum, čas od–do, popis práce, nakúpený materiál áno/nie), ktorý plní Google Sheet.
- Ďalšie vstupy: vystavené faktúry, prijaté faktúry, **výpisy z účtov jednotlivých firiem** (posiela banka), bločky niektorých firiem skenované hromadne na konci mesiaca.

### Princípy a dohody

- **Jeden veľký „master prompt“** popisujúci ~90 % funkčného produktu hneď na začiatku. Claude podľa neho navrhne architektúru. Iteratívne zmeny majú tendenciu rozbiť inú časť, preto sa nové funkcie dopĺňajú do master promptu a ten zostáva úplným popisom aplikácie. Je to dôležité aj pre budúcnosť, aby nové modely mohli opäť reprodukovať celý produkt na základe promptu.
- **Deterministika pred LLM**: čo sa dá riešiť skriptom (ID dokladu, QR kód, eKasa, číselné rady faktúr, párovanie bankových pohybov podľa VS/sumy/dátumu), rieši skript. LLM len tam, kde treba interpretáciu.
- **Paralelná prevádzka**: klient pokračuje vo svojom procese bez zmeny. Počas skúšobnej prevádzky platia za správne klientove existujúce podklady; aplikácia beží na **novom, čistom Google Drive** s rovnakou štruktúrou a jej výsledky sa s nimi porovnávajú, kým nie je spoľahlivá.
- **Inbox priečinok „na spracovanie“** (každá firma má vlastný), ktorý aplikácia v pevnom čase (napr. denne o 20:00) spracuje, roztriedi, porovná s databázou a označí spracované súbory. Ďalej sa pracuje s dátami v databáze, nie s obrázkami.
- **E-mail → Drive**: Gmail plus-adresa (napr. meno+faktury@gmail.com) pre dodávateľov; prílohy sa automaticky uložia do inboxu. Analogicky plus-adresa pre bankové výpisy (napr. meno+banka@gmail.com).
- **WhatsApp teraz nie je alfa a omega**. Prvá verzia: web (aj na mobile) so vstupnými sekciami (Faktúry, Bločky, Hodiny, Jazdy, Vozový park) a prehľadmi. Bločky a faktúry sa synchronizujú z Drive, hodiny a jazdy sa zatiaľ zadávajú ručne. Neskôr ich AI bude plniť z WhatsAppu.
- **Duplicity sa nevytvárajú, ale zisťujú**. Cieľom je vedieť, či je bloček zaevidovaný a či je fyzicky založený.
- **Človek v slučke**: automaticky spracované doklady čakajú v stave „na kontrolu“, kým ich klient nepotvrdí a nepriradí zákazky.
- **Jedna aktívna firma**: aplikácia eviduje viac firiem a ďalšie sa dajú kedykoľvek pridať. Používateľ vždy pracuje v jednej zvolenej firme a celé spracovanie (inbox, doklady, zákazky, náklady, výnosy, DPH, banka) sa týka len tejto firmy. Náklady medzi firmami neprechádzajú.
- **Aktívne / neaktívne záznamy (v1.1)**: zákazky, pracovníci, vozidlá, číselné rady, opakujúce sa faktúry a ďalšie číselníky majú príznak aktívny/neaktívny. **Neaktívne sa štandardne nezobrazujú** (ani v zoznamoch, ani vo výberových poliach formulárov); zobrazia sa len cez filter „zobraziť aj neaktívne“. Neaktívny záznam sa nikdy nemaže – historické náklady a výkazy na neho ostávajú naviazané.
- **Čas vo formáte 24 h (v1.1)**: všetky časy v UI aj výstupoch v 24-hodinovom formáte (HH:MM), dátumy DD.MM.RRRR, časové pásmo Europe/Bratislava. Žiadne AM/PM nikde, ani v natívnych time-pickeroch prehliadača (vlastný komponent).

## 2. Súhrn aplikácie a funkcionalít

### 2.1 Číselníky (master dáta)

- **Firmy**: ľubovoľný počet samostatných firiem (s.r.o.), ďalšie sa dajú kedykoľvek pridať. Každá má vlastné IČO, IČ DPH, údaj platiteľ DPH (áno/nie), číselné rady vystavených faktúr, vlastný inbox, vlastné bankové účty (IBAN) a vlastnú Réžiu. Používateľ vždy pracuje v jednej zvolenej **aktívnej firme** a všetko spracovanie sa týka len nej.
- **Odberatelia (zákazníci)**: názov, IČO, IČ DPH, adresa, kontakt, aktívny. Zákazka môže mať odberateľa (pre podklad k fakturácii a ziskovosť).
- **Zákazky / projekty**: názov, aliasy (ako ich ľudia píšu), firma (projekt patrí vždy práve jednej firme), odberateľ, rozpočet nákladov, **zmluvná / očakávaná cena pre zákazníka** (voliteľne), **typ fakturácie** (hodinovo – podľa výkazu / pevná cena / kombinácia), **default jednosmerná vzdialenosť v km** (napr. Sikorky ~25 km, tam a späť ~50 km), stav (napr. pripravovaná, prebiehajúca, ukončená), aktívny. Každá firma má špeciálnu zákazku **Réžia** pre náklady mimo zákaziek.
- **Pracovníci**: meno, aliasy, typ vzťahu (zamestnanec / živnostník / iné), **default nákladová sadzba** (koľko stojí firmu hodina), **default fakturačná sadzba** (koľko sa hodina účtuje zákazníkovi), aktívny. Obe sadzby sa môžu líšiť podľa človeka aj podľa zákazky (napr. Diesel robí lacnejšie). Pracovník môže pracovať pre viac firiem; jeho hodiny sa vždy evidujú vo firme, ktorej patrí zákazka.
- **Sadzby pracovníka na zákazke (v1.1)**: pre kombináciu pracovník + zákazka sa dá nastaviť samostatná **nákladová sadzba** aj samostatná **fakturačná sadzba**, s platnosťou od–do. Poradie hľadania sadzby: pracovník + zákazka (platná k dátumu) → default pracovníka (platná k dátumu).
- **Vozidlá**: evidované vo vozovom parku (2.5), vrátane firmy, sadzby €/km a príznaku aktívny.
- **Opakujúce sa (povinné) faktúry**: dodávateľ (Orange, Telekom, nájom a pod.), firma, očakávaná periodicita, aktívny.
- **Pravidlá priradenia firmy**: firma sa medzi firmami automaticky nepriraďuje. Doklad vždy patrí aktívnej firme, v ktorej používateľ práve pracuje (prišiel do jej inboxu alebo bol nahratý v nej). Ak IČO odberateľa na doklade nesedí s aktívnou firmou, doklad dostane upozornenie. IČO dodávateľa slúži len na návrh zákazky alebo Réžie.
- **Používatelia a roly**: admin/klient (všetko vrátane potvrdzovania dokladov, sadzieb, ziskovosti a fakturácie), pracovník (zadáva a vidí vlastné hodiny a jazdy, vidí svoj výkaz; nevidí sadzby iných, ziskovosť ani doklady). Používateľ s rolou pracovník je prepojený na záznam pracovníka.

### 2.2 Bločky

- Vstup: fotka alebo sken z Drive inboxu, neskôr z WhatsApp skupiny zákazky. Bločky sa musia dať načítať aj ako PDF. PDF s textovou vrstvou (e-shopy) sa číta priamo bez OCR; sken v PDF sa konvertuje na obrázok pre OCR.
- Extrakcia: obchod, IČO, dátum, čas, suma, DPH podľa sadzieb, **všetky položky** (názov, množstvo, cena), **ID dokladu / eKasa QR**.
- Bloček sa najprv skúsi načítať cez **API Finančnej správy (eKasa)** podľa ID dokladu, následne cez **Claude API**. Ak eKasa funguje, má prednosť; ak nie, nasleduje Claude API. Pri každom bločku je viditeľné, čo fungovalo. eKasa sa týka len bločkov, nie faktúr.
- **Priradenie zákazky**:
  - default: celý bloček na jednu zákazku,
  - prepínač „zmiešaný bloček“: každá položka na inú zákazku tej istej firmy,
  - jedna položka sa dá rozdeliť na viac zákaziek podľa podielu alebo množstva; tlačidlo **„rozdeliť rovnomerne“** pre položky spoločné pre viac zákaziek (napr. lepiaca páska). Súčet rozdelení = suma položky.
- Zdroj zákazky v poradí: ručná poznámka klienta na bločku alebo v názve súboru → WhatsApp skupina, z ktorej prišiel → návrh AI → otázka klientovi.
- **Detekcia duplicít** podľa ID dokladu z QR (deterministicky), záložne podľa kombinácie IČO + dátum + čas + suma. Duplicita sa nezakladá, ale doklad dostane príznak.
- **Evidencia fyzického dokladu**. Každý bloček má jeden z troch stavov:
  - zaevidovaný a fyzicky založený,
  - zaevidovaný (fotka od pracovníka), fyzicky chýba → upozornenie,
  - fyzicky naskenovaný, predtým nezaevidovaný → nový záznam.
- Rýchla kontrola: klient len naskenuje QR alebo odfotí bloček a systém povie „už máš, prišiel vtedy a vtedy od X“ a označí ho ako fyzicky založený.

### 2.3 Faktúry

- **Prijaté faktúry**: z e-mailu (plus-adresa → Drive inbox) alebo nafotené / naskenované.
- **Povinné opakujúce sa faktúry** (Orange, Telekom, nájom, …): idú do Réžie príslušnej firmy, nepriraďujú sa zákazkám. Ak v danom mesiaci chýba, systém **upozorní** („tento mesiac chýba faktúra za nájom“).
- **Nepovinné faktúry** (Hagard, SC Tech, Alza, …): spracujú sa ako bloček, teda zákazka na celú faktúru alebo po položkách. Klient sa snaží mať 1 faktúru = 1 zákazka (dodávateľ rozdelí), ale systém musí zvládnuť aj zmiešanú faktúru.
- Zákazka sa číta z textovej poznámky, ktorú klient dopíše do PDF, z textu faktúry, alebo sa systém opýta.
- **Vystavené faktúry**: firma je vždy jasná, je to aktívna firma. Číselný rad určuje projekt alebo oddelenú časť firmy, napr. dve osoby v jednej firme vystavujú faktúry každá vo vlastnom číselnom rade. Priradenie radu k projektu alebo časti firmy je deterministické.
- **Vystavená faktúra ako výnos zákazky (v1.1)**: vystavená faktúra (alebo jej položky) sa priradí k zákazke rovnakým alokačným mechanizmom ako náklady. Suma bez DPH (u platiteľa) je výnos zákazky pre prehľad ziskovosti. Vystavená faktúra môže byť naviazaná na podklad k fakturácii (2.9), z ktorého vznikla.
- Výnimky (napr. klimatizácia susedovi na firmu) klient označí ako Réžia.

### 2.4 Hodiny (dochádzka)

- Záznam: pracovník, zákazka, dátum, **čas od–do (24 h) alebo počet hodín**, popis práce, nakúpený materiál áno/nie, príznak **fakturovať zákazníkovi** (default áno; napr. oprava vlastnej chyby = nie).
- Náklad = hodiny × **nákladová sadzba** (podľa pracovníka a prípadne zákazky, platná k dátumu).
- Fakturovateľná hodnota = fakturovateľné hodiny × **fakturačná sadzba** (podľa pracovníka a prípadne zákazky, platná k dátumu).
- Sadzby sa k záznamu **zafixujú v čase výpočtu** (snapshot), aby neskoršia zmena sadzby nepreprepísala už vyfakturované alebo uzavreté obdobie; prepočet je možný len vedome (akcia „prepočítať sadzby za obdobie“, zapísaná do audit logu).
- V1: ručné zadanie cez webový formulár (náhrada Google formulára). Neskôr: AI parsuje denné správy z WhatsApp chatov „Hodiny“ a pri nejasnostiach sa doplňujúco pýta.
- Upozornenie na neúplný záznam (chýba začiatok alebo koniec, chýba zákazka).
- Ak je pri zázname „nakúpený materiál: áno“ a do X dní (nastaviteľný parameter) k danej zákazke a dňu neexistuje žiadny bloček ani faktúra, aplikácia upozorní na chýbajúci doklad.

### 2.5 Jazdy a vozový park

- Záznam jazdy: vozidlo, zákazka, dátum, vodič, posádka, km (nepovinné).
- **Ak km nie sú zadané**, dopočítajú sa z default jednosmernej vzdialenosti zákazky: **2 × vzdialenosť + 10 %** (10 % je nastaviteľný parameter). Ak sú km zadané, majú prednosť.
- Náklad = km × sadzba vozidla.
- Jedna jazda = jedno vozidlo, bez ohľadu na počet ľudí v ňom. Viac áut na zákazke = viac záznamov. Jazdu eviduje vodič.
- Náklad dopravy sa počíta z km, **nie z tankovaní**. Bločky za naftu sú len doklad pre DPH, nepriraďujú sa zákazke, aby sa náklad nepočítal dvakrát, a navrhnú sa do Réžie aktívnej firmy. Rovnako náklady na servis, PZP a diaľničné známky idú do Réžie (sú pokryté sadzbou €/km), nie do zákaziek.
- **Vozový park**: prehľad a evidencia vozidiel – pomenovanie, výrobca, model, ŠPZ, VIN, firma, náklad na km, platnosť STK, platnosť EK, aktuálny stav tachometra, poznámky, aktívny – s možnosťou tieto údaje editovať.
- **PZP (v1.1)**: ku každému vozidlu evidencia povinného zmluvného poistenia – poisťovňa, číslo zmluvy, ročná suma (poistné), platnosť od–do, periodicita platby, voliteľne naviazaný doklad. História zmlúv ostáva (nová zmluva = nový záznam). Rovnaká štruktúra je pripravená aj pre havarijné poistenie (typ poistenia).
- **Diaľničné známky (v1.1)**: ku každému vozidlu evidencia známok – krajina (default SK), typ (ročná / 30-dňová / 10-dňová / iná), platnosť od–do, cena, ŠPZ, na ktorú je známka vydaná, voliteľne naviazaný doklad.
- **Servis vozidla (v1.1)**: servisné záznamy – dátum, stav km, typ (pravidelný servis, oprava, pneumatiky, iné), popis, dodávateľ, cena, naviazaný doklad (prijatá faktúra / bloček). Plánovaný ďalší servis podľa dátumu a/alebo km; upozornenie, keď sa blíži.
- **Upozornenia vozového parku (v1.1)**: blížiaca sa alebo prekročená platnosť STK, EK, PZP, diaľničnej známky a termín servisu (predstih nastaviteľný, napr. 30 dní). Zobrazujú sa na dashboarde a v mesačnej kontrole.
- **Overenie údajov vozidla cez verejné služby (v1.1)**: modul „overenie vozidla“ podľa ŠPZ (prípadne VIN) overí údaje proti verejným overovacím službám (platnosť diaľničnej známky, platnosť PZP, platnosť STK/EK – podľa toho, ktoré služby sú dostupné). Implementácia ako samostatný adaptér na každú službu: ak služba poskytuje API, overenie je automatické (ručne aj plánovane) a výsledok sa porovná s evidenciou a pri nezhode vznikne upozornenie; ak API nie je, UI ponúkne priamy odkaz na overovaciu stránku s predvyplnenou ŠPZ. Výsledok a čas posledného overenia sa ukladá. Žiadne obchádzanie CAPTCHA ani scrapovanie v rozpore s podmienkami služby.

### 2.6 Prehľad zákaziek

- Náklady na zákazku spolu a po zložkách (materiál z bločkov, materiál z faktúr, práca, doprava) za ľubovoľné obdobie.
- Porovnanie s rozpočtom a zostatok.
- Možnosť rozkliknúť detail až na jednotlivý doklad, položku, hodinu a jazdu.

### 2.7 Ziskovosť (v1.1)

- **Na zákazku**: výnosy (vystavené faktúry priradené k zákazke, bez DPH u platiteľa) − náklady (materiál + práca + doprava) = hrubý zisk, marža v %. Za ľubovoľné obdobie.
- **Nevyfakturované**: hodnota vykonanej, ešte nevyfakturovanej práce a materiálu (z podkladu k fakturácii) – zobrazená zvlášť ako „rozpracovanosť“, aby bolo vidno aj očakávaný zisk, nielen realizovaný.
- **Pri pevnej cene**: porovnanie zmluvnej ceny s doterajšími nákladmi a odhad marže.
- **Celkovo za firmu**: súhrn všetkých zákaziek + Réžia (náklady Réžie znižujú celkový zisk firmy; voliteľne sa dajú zobraziť rozpočítané na zákazky pomerom k hodinám alebo nákladom – zobrazenie, nie zápis).
- Rozpad podľa mesiacov, porovnanie zákaziek medzi sebou, rozklik až na doklady a hodiny.
- Prístupné len pre rolu admin/klient.

### 2.8 DPH, banka a podklady pre účtovníctvo

- Mesačný prehľad DPH za každú firmu zvlášť (vstup / výstup).
- **Mesačná kontrola**: chýbajúce povinné faktúry, bločky bez fyzického originálu, doklady čakajúce na kontrolu, hlásené nákupy materiálu bez dokladu, bankové pohyby bez dokladu, upozornenia vozového parku.
- Bločky, ktoré sa skenujú hromadne na konci mesiaca, sa nahrajú do inboxu príslušnej firmy.
- **Bankové výpisy (v1.1, presunuté do V1)**: výpisy posiela banka (e-mailom → plus-adresa → bankový inbox firmy na Drive, alebo ručný upload). Podporované formáty v poradí preferencie: XML CAMT.053 (ISO 20022), CSV/XLSX podľa banky, PDF (posledná možnosť, cez extrakciu). Účet sa podľa IBAN priradí firme; ak IBAN nepatrí aktívnej firme, výpis sa nespracuje a vznikne upozornenie.
  - Každý pohyb sa uloží (dátum, suma, mena, protistrana, IBAN protistrany, VS/SS/KS, správa pre prijímateľa, typ – platba kartou / prevod / poplatok / iné).
  - **Párovanie deterministicky**: výdavok ↔ prijatá faktúra alebo bloček (VS = číslo faktúry, suma, dátum ± N dní, IČO/IBAN dodávateľa, pri kartových platbách obchodník + suma + dátum); príjem ↔ vystavená faktúra (VS, suma). LLM len ako návrh pri nejasných prípadoch; vždy s potvrdením.
  - **Výstup „čo chýba“**: zoznam pohybov bez dokladu (napr. platba kartou v OBI bez bločku), dokladov bez platby (neuhradené faktúry) a nezhôd v sume. Pohyby, ktoré doklad nepotrebujú (poplatky banky, mzdy, odvody, prevody medzi vlastnými účtami), sa dajú označiť a pre opakujúce sa prípady uložiť ako pravidlo.
  - Prijaté a vystavené faktúry dostanú stav úhrady (neuhradená / čiastočne / uhradená) z párovania.

### 2.9 Podklad k fakturácii a výstupy (v1.1)

- **Podklad k fakturácii zákazníkovi** (na zákazku, za obdobie): fakturovateľné hodiny po pracovníkoch alebo po dňoch × fakturačná sadzba, materiál (potvrdené doklady priradené k zákazke, s nastaviteľnou prirážkou % na zákazku, default z nastavení), doprava (km × fakturačná sadzba za km, ak sa fakturuje), súčet bez DPH, DPH, s DPH. Pri pevnej cene: prehľad vykonanej práce bez ocenenia.
  - Položky, ktoré už boli vyfakturované, sa označia (väzba na vystavenú faktúru), aby sa nič nefakturovalo dvakrát. Podklad sa dá „uzavrieť“ → jeho položky dostanú príznak fakturované.
  - Export: PDF (na odoslanie / vloženie do faktúry) a XLSX/CSV.
- **Podklad pre pracovníka** (na pracovníka, za obdobie): odpracované hodiny po dňoch a zákazkách, popis práce, súčet hodín a suma podľa nákladovej sadzby – teda **koľko hodín a akú sumu bude pracovník fakturovať firme** (živnostník) alebo podklad k mzde (zamestnanec). Pracovník ho vidí vo svojom účte, admin ho vie exportovať (PDF, XLSX) a poslať.
- **Ďalšie výstupy**: export ľubovoľnej tabuľky z UI do XLSX/CSV podľa aktuálne nastavených stĺpcov a filtrov (pozri 2.11), mesačný súhrn DPH, zoznam „čo chýba“ z mesačnej kontroly a banky.

### 2.10 Spracovanie a kontrola

- Plánované spracovanie inboxu (napr. denne o 20:00) aj ručné spustenie.
- Každý automaticky spracovaný doklad má stav: **na kontrolu → potvrdený**. Do prehľadov zákaziek sa započítajú len potvrdené (alebo s príznakom „nepotvrdené“).
- Úprava každého poľa a položky v UI, **audit log** (história zmien).
- Pôvodný súbor zostáva uložený a naviazaný na záznam.

### 2.11 Používateľské rozhranie (v1.1)

**Logické celky.** Navigácia je rozdelená do pevných skupín; každá sekcia patrí práve do jednej:

| Skupina | Sekcie |
| --- | --- |
| Prehľady | Dashboard (upozornenia, rozpracované zákazky), Zákazky – náklady, Ziskovosť |
| Doklady | Na kontrolu, Bločky, Prijaté faktúry, Vystavené faktúry, Rýchla kontrola bločku (QR) |
| Práca a doprava | Hodiny, Jazdy |
| Vozový park | Vozidlá, PZP a poistenie, Diaľničné známky, Servis, Overenie vozidla |
| Financie | DPH, Banka (výpisy a párovanie), Mesačná kontrola |
| Výstupy | Podklad k fakturácii, Podklad pre pracovníka, Exporty |
| Číselníky | Firmy, Číselné rady, Odberatelia, Zákazky, Pracovníci a sadzby, Opakujúce sa faktúry |
| Nastavenia | Používatelia a roly, Parametre, Integrácie (Drive, Gmail, eKasa, banky), Audit log |

Výber aktívnej firmy je vždy viditeľný v hlavičke. Rola pracovník vidí len Hodiny, Jazdy a svoj podklad.

**Tabuľkové zobrazenie ako základ.** Každý zoznam (doklady, položky, hodiny, jazdy, vozidlá, číselníky, bankové pohyby, prehľady) je jeden spoločný komponent **DataTable** s týmito vlastnosťami:

- **Výber stĺpcov**: používateľ si z **všetkých dostupných polí entity** (vrátane polí z naviazaných entít, napr. pri hodine aj názov zákazky a odberateľa, a vypočítaných polí ako náklad) vyberie, ktoré stĺpce vidí, v akom poradí (drag & drop) a akej šírke.
- **Triedenie** podľa ľubovoľného stĺpca, aj viacúrovňové.
- **Filtrovanie** po stĺpcoch podľa typu poľa (text: obsahuje / rovná sa; číslo a suma: od–do; dátum: od–do a rýchle voľby „tento mesiac / minulý mesiac / tento rok“; výber: viac hodnôt; áno/nie) + fulltextové vyhľadávanie v tabuľke.
- **Uložené pohľady**: kombinácia stĺpcov, triedenia a filtrov sa dá uložiť pod menom (napr. „Sikorky – materiál tento mesiac“) a nastaviť ako predvolený. Pohľady sú per používateľ; admin môže pohľad zdieľať všetkým. Posledné nastavenie sa pamätá na serveri (nie len v prehliadači), aby fungovalo na mobile aj PC.
- **Súčty** v pätičke pre číselné stĺpce (súčet za vyfiltrované riadky, nie len aktuálnu stranu).
- **Zoskupenie** podľa stĺpca (napr. hodiny podľa zákazky alebo pracovníka) so súčtami skupín.
- **Filter aktívny/neaktívny** ako štandardný prepínač pri entitách s príznakom aktívny; default skryté neaktívne.
- **Export** aktuálneho pohľadu (stĺpce + filtre + triedenie) do XLSX/CSV.
- **Rozklik riadku** na detail (bočný panel alebo samostatná stránka) s editáciou, históriou zmien a naviazaným súborom; hromadné akcie nad označenými riadkami (napr. potvrdiť, priradiť zákazku, označiť fyzický originál).
- Stránkovanie, triedenie a filtrovanie sa robí **na serveri** (dáta môžu rásť).
- Na mobile sa tabuľka zobrazí ako zoznam kariet s 2–4 hlavnými stĺpcami podľa aktuálneho pohľadu; rýchle zadávanie hodín a jázd má na mobile jednoduchý formulár.

**Technické riešenie stĺpcov.** Backend má **register polí (field registry)** pre každú entitu: kľúč, popis v slovenčine, typ (text, číslo, suma, dátum, čas, výber, áno/nie, odkaz), či sa dá triediť a filtrovať, či je vypočítané, a ktoré roly ho smú vidieť (napr. sadzby a ziskovosť len admin). Endpoint `GET /api/meta/{entita}/fields` vráti dostupné polia pre danú rolu; zoznamové endpointy prijímajú jednotný formát parametrov `columns`, `sort`, `filter`, `page`. Nové pole v DB sa do UI dostane len pridaním do registra, bez zmeny frontendu. Pre tabuľky sa použije TanStack Table (headless) s vlastnými komponentmi.

**Ďalšie pravidlá UI**: slovenčina, čísla s desatinnou čiarkou a medzerou ako oddeľovačom tisícov, mena €, čas 24 h, dátumy DD.MM.RRRR, svetlý aj tmavý režim, ovládanie klávesnicou pri hromadnom zadávaní.

### 2.12 Neskoršie fázy (dohodnuté, nie vo V1)

- **WhatsApp integrácia**: hodiny z chatov pracovníkov, bločky a fotky zo skupín zákaziek.
- **AI asistent nad databázou**: otázky v prirodzenom jazyku („koľko sme minuli na Sikorky“, „aká je marža na Sikorkách“).
- **Týždenný report na zákazku** z WhatsApp skupín (čo sa spravilo, fotky). Report ide najprv klientovi na schválenie, potom zákazníkovi ako newsletter. Voliteľne, pre zákazky, ktoré to vyžadujú, slúži aj ako podklad do **stavebného denníka**.
- Priame napojenie na banky cez API (namiesto výpisov e-mailom).
- Napojenie na účtovníctvo.
- Vystavovanie faktúr priamo z aplikácie z uzavretého podkladu k fakturácii.

## 3. Návrh aplikácie

Návrh: jeden backend s REST API a PostgreSQL databázou ako jediným zdrojom pravdy aplikácie. Všetky vstupy (Drive inbox, e-mail, bankové výpisy, web formuláre, overovacie služby vozidiel, neskôr WhatsApp) sú samostatné adaptéry, ktoré len zapisujú cez API. Stack podľa už dohodnutého ICO-APP: **FastAPI (Python), PostgreSQL, React + TypeScript (responzívne, mobile-first), TanStack Table, Docker Compose, self-hosted Ubuntu**. Aplikácia podporuje viac firiem, ale používateľ vždy pracuje v jednej zvolenej firme. Každý záznam nesie firmu a API aj spracovanie pracujú len s údajmi aktívnej firmy; náklady medzi firmami neprechádzajú.

Architektúra (textovo):

```
Vstupy (adaptéry)                      Jadro                          Výstupy
---------------------------------      -------------------------      -----------------------------
Drive inbox (bločky, faktúry) ---\     |                       |      Web UI (tabuľky, prehľady)
Gmail plus-adresa -> Drive -------\    |  REST API (FastAPI)   |----> Dashboard zákaziek, ziskovosť
Bankové výpisy (CAMT/CSV/PDF) ---- >-->|  + plánovač úloh      |----> Podklad k fakturácii / pracovník
Web formuláre (hodiny, jazdy) ----/    |  PostgreSQL           |----> DPH, mesačná kontrola, banka
Overenie vozidla (adaptéry) -----/     |                       |----> Exporty XLSX / CSV / PDF
[neskôr] WhatsApp - - - - - - - -/     -------------------------      [neskôr] AI asistent, reporty
```

Dashboard zákaziek a ziskovosti je hlavný výstup V1.

### 3.1 Komponenty

| Komponent | Úloha | Deterministické / LLM |
| --- | --- | --- |
| Drive sync (ingest) | Raz denne (napr. 20:00) a na požiadanie stiahne nové súbory z inboxu každej firmy, uloží ich, zapíše hash, presunie do „spracované“ | Deterministické |
| E-mail → Drive | Gmail plus-adresa, prílohy faktúr a bankových výpisov automaticky do príslušného inboxu | Deterministické |
| PDF / obraz príprava | PDF s textovou vrstvou → text; sken → konverzia na obrázok | Deterministické |
| QR / eKasa modul | Dekóduje QR z bločku, získa ID dokladu, načíta doklad z eKasa (primárny zdroj pre bločky) | Deterministické |
| Extrakcia dokladu | OCR + štruktúra (hlavička, položky, DPH) z fotky / PDF; pri bločkoch záloha, ak eKasa zlyhá, pri faktúrach hlavný spôsob | LLM (Claude API, vision) |
| Aktívna firma a číselné rady | Doklad patrí aktívnej firme; kontrola IČO odberateľa voči aktívnej firme; číselný rad vystavenej faktúry → projekt alebo časť firmy | Deterministické |
| Návrh zákazky | Z poznámky, názvu súboru, zdroja (skupina), histórie dodávateľa; len zákazky aktívnej firmy | Najprv pravidlá, potom LLM |
| Detekcia duplicít | ID dokladu, záložne IČO + dátum + čas + suma, hash súboru | Deterministické |
| Kontrolná fronta | Doklady „na kontrolu“, potvrdenie, rozdelenie položiek (aj rovnomerne) | UI |
| Nákladový engine | Výpočet nákladov zákazky (materiál, práca, doprava) so snapshotom sadzieb | Deterministické (SQL) |
| Engine ziskovosti a fakturácie | Výnosy zákazky, zisk, marža, rozpracovanosť; podklad k fakturácii a pre pracovníka; značenie vyfakturovaných položiek | Deterministické |
| Banka – import a párovanie | Parsovanie CAMT.053 / CSV / PDF, priradenie účtu k firme podľa IBAN, párovanie pohybov s dokladmi, zoznam „čo chýba“, pravidlá pre pohyby bez dokladu | Deterministické; LLM len návrh pri PDF a nejasnom párovaní |
| Vozový park | Vozidlá, PZP/poistenie, diaľničné známky, servis, upozornenia na platnosti | Deterministické |
| Overenie vozidla | Adaptér na každú verejnú overovaciu službu (API alebo odkaz), porovnanie s evidenciou | Deterministické |
| Mesačná kontrola | Chýbajúce povinné faktúry, chýbajúce originály, doklady na kontrolu, nákup materiálu bez dokladu, bankové pohyby bez dokladu, upozornenia vozového parku | Deterministické |
| Register polí a pohľady | Metadáta polí entít pre UI, uložené pohľady tabuliek per používateľ, jednotné filtrovanie/triedenie/stránkovanie na serveri, export | Deterministické |
| Exporty | XLSX / CSV z ľubovoľného pohľadu, PDF podklady | Deterministické |
| Web UI | Výber aktívnej firmy · logické celky podľa 2.11 · univerzálna DataTable | — |
| Neskôr: WhatsApp adaptér | Hodiny z chatov, bločky a fotky zo skupín | LLM + potvrdenie |
| Neskôr: AI asistent a reporty | Otázky nad DB (cez API, nie priamo SQL), týždenné reporty | LLM |

### 3.2 Dátový model (jadro)

Všetky číselníkové entity majú pole `active` (bool, default true). Všetky entity okrem globálnych majú `company_id`.

| Entita | Kľúčové polia |
| --- | --- |
| company | názov, IČO, IČ DPH, platitel_dph (áno/nie), inbox priečinok, bankový inbox, adresa na faktúry |
| bank_account | firma, IBAN, banka, mena, aktívny |
| invoice_series | firma, označenie radu (napr. predpona čísla faktúry), projekt alebo časť firmy (napr. meno osoby, ktorá v rade vystavuje), aktívny |
| customer | firma, názov, IČO, IČ DPH, adresa, kontakt, aktívny |
| user | meno, e-mail, firmy, ku ktorým má prístup, rola (admin/klient, pracovník), väzba na worker (pri role pracovník) |
| project | názov, aliasy, firma (práve jedna), odberateľ, rozpočet nákladov, zmluvná cena, typ fakturácie (hodinovo / pevná cena / kombinácia), prirážka na materiál %, fakturácia dopravy (áno/nie, sadzba €/km), default_km_one_way, stav, aktívny (Réžia = špeciálny projekt, jeden na firmu) |
| worker | meno, aliasy, typ vzťahu (zamestnanec / živnostník / iné), IČO (pri živnostníkovi), aktívny |
| worker_rate | pracovník, projekt (voliteľne), **nákladová sadzba**, **fakturačná sadzba**, platnosť od–do |
| vehicle | pomenovanie, výrobca, model, ŠPZ, VIN, firma, sadzba €/km, platnosť STK, platnosť EK, stav km, poznámky, aktívny |
| vehicle_insurance | vozidlo, typ (PZP / havarijné), poisťovňa, číslo zmluvy, suma (poistné), periodicita platby, platnosť od–do, doklad (voliteľne) |
| vehicle_vignette | vozidlo, krajina, typ (ročná / 30-dňová / 10-dňová / iná), ŠPZ, platnosť od–do, cena, doklad (voliteľne) |
| vehicle_service | vozidlo, dátum, stav km, typ, popis, dodávateľ, cena, doklad (voliteľne), ďalší servis – dátum / km |
| vehicle_check | vozidlo, služba (známka / PZP / STK / EK), čas overenia, výsledok, nájdené údaje, zhoda s evidenciou (áno/nie) |
| source_file | firma, cesta na Drive, hash, zdroj (inbox, e-mail, bankový inbox, WhatsApp, upload), stav spracovania |
| document | typ (bloček, prijatá f., vystavená f.), firma (aktívna firma), dodávateľ / odberateľ, IČO, číslo / ID dokladu, číselný rad (pri vystavenej faktúre), eKasa ID, dátum, dátum splatnosti, VS, suma, DPH, zdroj_extrakcie (eKasa / Claude / ručne), stav (na kontrolu, potvrdený), stav úhrady, fyzický originál (áno/nie, dátum), duplicate_of |
| document_line | dokument, popis, množstvo, jedn. cena, sadzba DPH, suma |
| allocation | dokument alebo položka, projekt, podiel % alebo suma, smer (náklad / výnos) |
| billing_statement | firma, projekt, obdobie od–do, stav (návrh / uzavretý), vystavená faktúra (voliteľne), súčty |
| billing_statement_line | podklad, typ (hodiny / materiál / doprava / iné), odkaz na zdrojový záznam (timesheet_entry, allocation, trip), množstvo, sadzba, suma |
| recurring_invoice_rule | dodávateľ, firma, periodicita, posledný výskyt, aktívny |
| timesheet_entry | pracovník, projekt, dátum, od, do (24 h), hodiny, popis, materiál áno/nie, fakturovať (áno/nie), nákladová sadzba (snapshot), fakturačná sadzba (snapshot), fakturované v (billing_statement), zdroj |
| trip | vozidlo, projekt, dátum, vodič, posádka, km (null = 2 × default_km_one_way projektu + 10 %), sadzba (snapshot), fakturované v, zdroj |
| bank_statement | firma, účet, obdobie, zdrojový súbor, formát |
| bank_transaction | výpis, dátum, suma, mena, protistrana, IBAN protistrany, VS/SS/KS, správa, typ, stav (spárovaný / bez dokladu / nepotrebuje doklad), poznámka |
| transaction_match | pohyb, dokument, suma, spôsob (automaticky / ručne / návrh), potvrdené |
| transaction_rule | firma, podmienka (protistrana / IBAN / text / typ), akcia (nepotrebuje doklad / návrh zákazky / návrh dodávateľa), aktívny |
| table_view | používateľ, entita, názov, stĺpce (poradie, šírka), triedenie, filtre, zoskupenie, predvolený, zdieľaný |
| setting | globálne a firemné parametre (napr. prirážka k default vzdialenosti 10 %, počet dní na doloženie dokladu k nákupu materiálu, default prirážka na materiál, predstih upozornení vozového parku, tolerancia dní pri párovaní banky) |
| audit_log | kto, kedy, čo zmenil (entita, id, pole, stará a nová hodnota) |

`allocation` je kľúčová: rieši celý doklad na 1 zákazku, zmiešaný doklad po položkách aj rozdelenie jednej položky na viac zákaziek (vrátane rovnomerného) jedným mechanizmom – pre náklady (prijaté doklady) aj výnosy (vystavené faktúry). Platí kontrola, že súčet alokácií = suma dokladu. Priradiť sa dajú len zákazky aktívnej firmy, takže náklad ani výnos nikdy neprejde do inej firmy.

### 3.3 Výpočet nákladov, výnosov a zisku zákazky

- **Materiál** = súčet nákladových alokácií potvrdených dokladov (bez DPH, ak je firma platiteľ, inak s DPH).
- **Práca** = Σ hodiny × nákladová sadzba (snapshot; najprv sadzba pracovník + projekt, inak default pracovníka, platná k dátumu).
- **Doprava** = Σ (km jazdy, alebo 2 × default_km_one_way projektu × 1,10) × sadzba vozidla.
- Tankovania, servis, PZP a známky sa do zákazky nezapočítavajú (Réžia). Bločky od čerpacích staníc sa automaticky navrhnú do Réžie aktívnej firmy.
- **Výnos** = súčet výnosových alokácií vystavených faktúr (bez DPH u platiteľa).
- **Rozpracovanosť** = nevyfakturované fakturovateľné hodiny × fakturačná sadzba + nevyfakturovaný materiál × (1 + prirážka) + nevyfakturovaná doprava (ak sa fakturuje).
- **Zisk** = výnos − (materiál + práca + doprava); **marža** = zisk / výnos.

### 3.4 Tok spracovania dokladu

1. Súbor príde do inboxu aktívnej firmy (Drive, e-mail, neskôr WhatsApp).
2. Ingest uloží súbor, spočíta hash. Rovnaký súbor sa ďalej nespracúva.
3. PDF s textovou vrstvou sa číta ako text; sken alebo fotka sa pripraví ako obrázok.
4. Bloček: QR modul získa ID dokladu. Ak rovnaké ID už existuje, záznam sa nezakladá, len sa doplní zdroj a prípadne príznak „fyzický originál“.
5. Bloček: načítanie z eKasa podľa ID. Ak eKasa zlyhá alebo QR nie je čitateľný, Claude API prečíta doklad vrátane ID dokladu a s týmto ID sa eKasa skúsi znova (a znova sa skontroluje duplicita). Faktúra: Claude API, prípadne text z PDF.
6. Kontrola: súčet položiek = suma, DPH sedí. Zapíše sa zdroj_extrakcie.
7. Doklad patrí aktívnej firme; ak IČO odberateľa nesedí, dostane upozornenie. Návrh zákazky (len zo zákaziek aktívnej firmy) ide z poznámky, zdroja, histórie, inak LLM.
8. Doklad ide do fronty **Na kontrolu**. Klient potvrdí, upraví, rozdelí položky.
9. Potvrdený doklad vstupuje do prehľadu zákaziek, ziskovosti, DPH a párovania s bankou aktívnej firmy.

### 3.5 Tok spracovania bankového výpisu (v1.1)

1. Výpis príde do bankového inboxu (e-mail → Drive) alebo cez upload.
2. Ingest uloží súbor a hash; rovnaký výpis sa nespracuje znova, prekrývajúce sa pohyby sa deduplikujú (dátum + suma + referencia banky).
3. Podľa IBAN sa určí firma; ak nepatrí aktívnej firme, upozornenie a koniec.
4. Parsovanie podľa formátu (CAMT.053 → CSV → PDF cez extrakciu).
5. Aplikácia pravidiel `transaction_rule` (napr. poplatky, mzdy → nepotrebuje doklad).
6. Deterministické párovanie s dokladmi; nejednoznačné prípady ako návrh.
7. Výsledok v sekcii Banka a v mesačnej kontrole: spárované, návrhy na potvrdenie, **pohyby bez dokladu**, **doklady bez platby**.

### 3.6 Fázy (odporúčané poradie)

1. **Základ**: DB, API, prihlásenie, používatelia a roly, výber aktívnej firmy, register polí + univerzálna DataTable (výber stĺpcov, triedenie, filtre, uložené pohľady, export, filter aktívny/neaktívny), číselníky (firmy, číselné rady, odberatelia, zákazky, pracovníci, nákladové a fakturačné sadzby, vozový park vrátane PZP, známok a servisu), import zoznamov od klienta.
2. **Hodiny + Jazdy** (ručné zadávanie, 24 h, náhrada Google formulára) **+ dashboard zákaziek + podklad pre pracovníka**. Hodiny sú najväčšia nákladová položka, takže klient má hneď použiteľný prehľad.
3. **Bločky**: Drive inbox, PDF príprava, QR/eKasa, extrakcia cez Claude API ako záloha, duplicity, fyzický originál, kontrolná fronta, rozdelenie po položkách.
4. **Faktúry**: e-mail → Drive, povinné opakujúce sa faktúry s upozornením, vystavené faktúry podľa číselného radu a ich priradenie k zákazke → **ziskovosť** a **podklad k fakturácii**.
5. **DPH, banka a mesačná kontrola** po firmách: import výpisov, párovanie, „čo chýba“.
6. **Vozový park – upozornenia a overenie vozidla** cez verejné služby.
7. **WhatsApp**: hodiny z chatov, bločky zo skupín (s potvrdením).
8. **AI asistent, týždenné reporty, stavebný denník, bankové API, účtovníctvo, vystavovanie faktúr**.

Každá fáza sa dodáva s testovacím postupom a beží paralelne s klientovým existujúcim procesom, kým nie je overená.

## 4. Otvorené body (doplniť pred implementáciou dotknutej časti)

- „Nákladovosť na …“ – pripomienka zákazníka je nedopísaná (na čo: na hodinu, na km, na m², na pracovníka, na vozidlo?).
- Fakturačná logika: prirážka na materiál, fakturácia dopravy, pevné ceny – potvrdiť so zákazníkom.
- Overenie vozidla: ktoré údaje a cez ktoré služby; dostupnosť API.
- Banky a formáty výpisov jednotlivých firiem.

## 5. Zmeny vo verzii 1.1

Pripomienky zákazníka:

| Pripomienka | Kde je zapracovaná |
| --- | --- |
| Podklad k fakturácii | 2.9, 3.2 (billing_statement), 3.3 |
| Prehľad ziskovosti – celkovo / na zákazke | 2.7, 3.3 |
| Filter aktívny/neaktívny – neaktívnych nevidím | Princípy, 2.1, 2.11, 3.2 (`active`) |
| Nákladová sadzba na pracovníka na zákazke | 2.1, 2.4, 3.2 (worker_rate) |
| Výstupy (podklad pre zamestnanca, koľko hodín bude fakturovať) | 2.9 |
| Vozidlá – overenie cez nejakú stránku | 2.5, 3.1, 3.2 (vehicle_check) |
| Vozidlá – PZP: poisťovňa, číslo zmluvy, suma, platnosť | 2.5, 3.2 (vehicle_insurance) |
| Diaľničná známka | 2.5, 3.2 (vehicle_vignette) |
| Hodiny – formát času 24 h | Princípy, 2.4, 2.11 |
| Servis vozidla | 2.5, 3.2 (vehicle_service) |
| Nákladovosť na (nedopísané) | Otvorené body (4) |
| Výpisy z účtov – kontrola voči dokladom, čo chýba | 2.8, 3.5; presunuté z neskorších fáz do V1 (fáza 5) |

Požiadavky na UI: logické celky navigácie a univerzálne tabuľkové zobrazenie s výberom stĺpcov z dostupných polí, triedením, filtrovaním, uloženými pohľadmi a exportom – 2.11, 3.1, 3.2 (table_view), fáza 1.

Ďalej: `cost_allocation` premenovaná na `allocation` so smerom náklad/výnos; nová entita odberateľ; snapshot sadzieb na hodinách a jazdách; servis, PZP a známky idú do Réžie.
