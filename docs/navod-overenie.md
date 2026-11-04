# Návod na overenie aplikácie

Postup na vyskúšanie hlavných funkcií. Predpoklad: aplikácia beží podľa README (`docker compose up -d --build`) a ste prihlásený ako administrátor.

Najrýchlejšie je overovať na demo dátach:

```bash
docker compose exec app python -m app.cli seed-demo
```

Potom v hlavičke zvoľte firmu **Demo Stavby s.r.o.** Ak chcete overovať na vlastných dátach, postupujte podľa README, kapitola 3 (Prvé kroky).

---

## 1. Základ: firmy, číselníky, tabuľky

1. *Číselníky → Firmy*: založte novú firmu. V *Číselníky → Zákazky* sa pri nej automaticky objaví zákazka **Réžia**.
2. Prepnite aktívnu firmu v hlavičke. Zoznamy zákaziek, dokladov a hodín sa zmenia, pretože dáta medzi firmami neprechádzajú.
3. Na ľubovoľnej tabuľke (napr. *Práca a doprava → Hodiny*) vyskúšajte:
   - **Stĺpce**: pridajte napríklad „Odberateľ“ alebo „Fakturovateľná hodnota“ a zmeňte poradie ťahaním.
   - **Šírku stĺpca**: potiahnite pravý okraj hlavičky.
   - **Triedenie**: klik na hlavičku, Shift + klik pridá ďalšiu úroveň.
   - **Filter**: Dátum → „tento mesiac“, Zákazka → vybrané hodnoty, Hodiny od–do.
   - **Hľadať**: fulltextové vyhľadávanie v tabuľke.
   - **Zoskupiť**: podľa zákazky alebo pracovníka, so súčtami skupín.
   - **Súčty** v pätičke sú za všetky vyfiltrované riadky, nie len za aktuálnu stranu.
   - **Pohľady**: uložte nastavenie pod menom a označte ho ako predvolený. Po odhlásení a prihlásení, aj na mobile, sa nastavenie zachová.
   - **XLSX / CSV**: export presne aktuálneho pohľadu.
4. *Číselníky → Zákazky*: deaktivujte zákazku (ikona koša v detaile). Zo zoznamu aj z výberov zmizne a vrátite ju cez „zobraziť aj neaktívne“. Nikdy sa nemaže.
5. V detaile záznamu otvorte záložku **História zmien** (audit log).

## 2. Hodiny a jazdy

1. *Hodiny → Rýchle zadanie*: zadajte čas `7` a `1530`. Hodiny sa dopočítajú na 8,5 a čas je vždy 24-hodinový (žiadne AM/PM).
2. Po uložení ostane dátum, pracovník aj zákazka predvyplnená pre ďalší záznam (Ctrl + Enter uloží).
3. V tabuľke zobrazte stĺpce „Nákladová sadzba“ a „Fakturačná sadzba“. Demo pracovník *Diesel* má na zákazke Sikorky nákladovú sadzbu 11 €/h a inde 12 €/h.
4. **Snapshot sadzieb:** v *Číselníky → Sadzby pracovníkov* zmeňte Dieselovi sadzbu. Staré hodiny sa nezmenia. Prepočítate ich až vedome: označte riadky v Hodinách → **Prepočítať sadzby** (zapíše sa do audit logu).
5. *Jazdy*: zadajte jazdu bez km na zákazku Sikorky (25 km). Použije sa 2 × 25 + 10 % = **55 km** × sadzba vozidla. Ak km zadáte, majú prednosť.
6. Prihláste sa ako pracovník (účet vytvoríte v *Nastavenia → Používatelia*, rola Pracovník, prepojený pracovník). Pracovník vidí len Hodiny, Jazdy a svoj podklad, iba vlastné záznamy a bez fakturačných sadzieb.

## 3. Bločky a faktúry

1. *Doklady → Na kontrolu → Nahrať doklady*: nahrajte fotku bločku s QR kódom.
   - V detaile dokladu, v časti „Priebeh spracovania“, vidno, čo fungovalo: QR → eKasa → Claude API.
   - Bez `ANTHROPIC_API_KEY` sa doklad bez eKasy založí na ručné doplnenie.
2. Ak má súbor v názve zákazku (napr. `sikorky_blocek.jpg`), zákazka sa navrhne automaticky. Bločky z čerpacích staníc sa navrhnú do **Réžie**.
3. Detail dokladu:
   - priradenie celého dokladu na zákazku, alebo **zmiešaný doklad** po položkách,
   - **Rozdeliť rovnomerne** rozdelí položku na viac zákaziek (kontrola, že súčet = suma položky),
   - **Potvrdiť a ďalší** prejde na ďalší doklad na kontrolu. Do prehľadov sa započítajú len potvrdené doklady.
4. **Duplicity:** nahrajte ten istý bloček znova (iná fotka, rovnaký QR) so zaškrtnutým „sken fyzického originálu“. Nový doklad nevznikne, súbor sa pripojí k existujúcemu a ten sa označí ako fyzicky založený.
5. *Doklady → Rýchla kontrola bločku*: odfoťte QR alebo zadajte ID `O-…`. Aplikácia odpovie „Už máš – prišiel vtedy a vtedy“.
6. *Vystavené faktúry*: číslo faktúry sa podľa predpony priradí k **číselnému radu** (napr. `P2026…` → rad osoby Peter). Priradením k zákazke vzniká **výnos**.
7. *Číselníky → Opakujúce sa faktúry*: ak faktúra (napr. Orange) v mesiaci chýba, zobrazí sa na Dashboarde aj v Mesačnej kontrole.

## 4. Prehľady

1. *Zákazky – náklady*: materiál z bločkov a faktúr, práca, doprava, rozpočet a zostatok. Klik na zákazku zobrazí detail až po doklad, položku, hodinu a jazdu.
2. *Ziskovosť*: výnosy − náklady, marža, **rozpracovanosť** (nevyfakturovaná práca, materiál s prirážkou a doprava) a očakávaný zisk. Pri pevnej cene sa zobrazí odhad marže. Réžia znižuje zisk firmy a dá sa rozpočítať podľa hodín alebo nákladov (len zobrazenie).

## 5. Fakturácia a výstupy

1. *Výstupy → Podklad k fakturácii*: vyberte zákazku a obdobie a skontrolujte náhľad. **Vytvoriť podklad** → PDF / XLSX / CSV.
2. **Uzavrieť**: položky dostanú príznak vyfakturované. Nový podklad za rovnaké obdobie ich už neponúkne a hodiny vo vyfakturovanom podklade sa nedajú meniť. **Otvoriť** to vráti späť.
3. *Výstupy → Podklad pre pracovníka*: hodiny po dňoch a zákazkách a suma podľa nákladovej sadzby (PDF / XLSX).

## 6. Banka, DPH, mesačná kontrola

1. *Číselníky → Bankové účty*: pridajte IBAN firmy.
2. *Financie → Banka → Importovať výpis* (CAMT.053 XML, CSV, XLSX): pohyby sa deterministicky spárujú podľa VS, sumy, dátumu, IBAN a názvu.
   - Záložka **Čo chýba**: pohyby bez dokladu, faktúry bez úhrady a nezhody v sume.
   - Poplatky a mzdy označte „Nepotrebuje doklad“ a uložte ako pravidlo.
   - Výpis s IBAN inej firmy sa odmietne.
3. *Financie → DPH*: mesačný vstup a výstup po sadzbách.
4. *Financie → Mesačná kontrola*: chýbajúce povinné faktúry, bločky bez originálu, doklady na kontrolu, nákup materiálu bez dokladu (po X dňoch), neúplné hodiny, banka a vozový park.

## 7. Vozový park

1. *Vozidlá, PZP a poistenie, Diaľničné známky, Servis*: evidencia s históriou.
2. *Overenie vozidla*: upozornenia na blížiace sa alebo prekročené platnosti (STK, EK, PZP, známka, servis podľa dátumu alebo km). Tlačidlo **Overiť** otvorí verejnú službu (ŠPZ sa skopíruje). **Zapísať výsledok** uloží overenie a porovná ho s evidenciou.

## 8. Google Drive / Gmail

Po nastavení podľa README (kapitola 4) vložte súbor do Drive priečinka „na spracovanie“ alebo pošlite e-mail s prílohou na `meno+<tag>@gmail.com`. Potom kliknite na *Doklady → Inbox a súbory → Spracovať inbox teraz*. Súbor sa presunie do „spracované“ a doklad sa objaví v časti Na kontrolu.
