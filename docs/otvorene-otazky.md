# Otvorené otázky

Projekt: Evidencia a výdaj barelov s vodou. Stav k 2. 10. 2026. Q-01 až Q-08 sú vyriešené (ID sa nepoužíva znova).
Súvisiace dokumenty: `funkcne-poziadavky-evidencia-barelov.md` (v0.2), `CLAUDE.md`.

## Ako s týmto súborom pracovať

- Každá otázka má **návrh**. Ak sa nerozhodneme inak, platí návrh.
- Po rozhodnutí sa otázka presunie do sekcie **Rozhodnuté** a premietne sa do požiadaviek a `CLAUDE.md`.
- Ak otázka blokuje prácu na danej fáze, Claude nehádaj. Spýta sa.

## Prehľad

| ID | Téma | Treba vyriešiť pred | Blokuje? |
|---|---|---|---|
| Q-09 | Odovzdanie faktúry a jej náležitosti | Fáza 6 | Nie pre demo |
| Q-10 | Uchovávanie záznamov a GDPR | Pred ostrým nasadením | Nie pre demo |
| Q-11 | Externí zákazníci | Pred ich spustením | Nie pre demo |
| Q-12 | Informovanie zamestnancov o Supervízorovi | Pred fázou 8 | Nie pre demo |

---

## Q-09 Odovzdanie faktúry a jej náležitosti

**Otázka:** Ako sa faktúra odovzdáva fakturačnému oddeleniu (e-mail, export, účtovný systém) a aké zákonné náležitosti musí mať (DPH, IČO/DIČ, číselný rad, splatnosť)?

**Prečo na tom záleží:** V deme je faktúra len položkový dokument. Pre ostrú prevádzku treba presné pravidlá.

**Návrh:** V deme len zmena stavu na „odoslaná" a notifikácia, bez integrácie. Náležitosti a spôsob odovzdania treba overiť s účtovníctvom pred fázou 6, aby sme dátový model faktúry nemuseli neskôr prerábať.

**Rozhodnutie:** zatiaľ nie

---

## Q-10 Uchovávanie záznamov a GDPR

**Otázka:** Aká konkrétna environmentálna legislatíva vyžaduje evidenciu barelov a ako dlho sa záznamy musia uchovávať? Ako to zladiť s GDPR pri deaktivovaných používateľoch, keď sa nič nemaže?

**Prečo na tom záleží:** Pravidlo „nič sa nemaže" sa môže dostať do konfliktu s právom na výmaz osobných údajov.

**Návrh:** Overiť s právnikom. Technické riešenie, ktoré tento konflikt zvyčajne rieši: záznamy o baroch, výpožičkách a pokutách sa zachovajú, no osobné údaje deaktivovaného používateľa sa po uplynutí lehoty anonymizujú. Toto nie je právne poradenstvo.

**Rozhodnutie:** zatiaľ nie

---

## Q-11 Externí zákazníci

**Otázka:** Čo treba doriešiť, keď sa začne predávať externým zákazníkom?

**Prečo na tom záleží:** Externí menia pravidlá registrácie, ochrany údajov a platieb.

**Návrh:** Pred spustením doriešiť schvaľovanie registrácie, overenie e-mailom, súhlasy podľa GDPR, cenník, DPH a online platby. V MVP sa pripravuje len dátový model (typ zákazníka, voliteľné fakturačné údaje).

**Rozhodnutie:** zatiaľ nie

---

## Q-12 Informovanie zamestnancov o Supervízorovi

**Otázka:** Ako sa zamestnanci dozvedia, že Supervízor sleduje ich prácu a že sa jeho prístupy logujú?

**Návrh:** Interná smernica alebo oznámenie pred nasadením roly Supervízor. Treba to konzultovať s HR alebo právnikom. Toto nie je právne poradenstvo.

**Rozhodnutie:** zatiaľ nie

---

# Rozhodnuté

| Téma | Rozhodnutie |
|---|---|
| Počet rolí | Päť: Super admin, Skladník, Fakturant, Supervízor, Používateľ |
| Zmena vlastnej roly | Super admin ju nemôže meniť, zmeny rolí idú do auditu |
| Kombinácie rolí | Zakázané: Skladník + Fakturant, Supervízor s ostatnými (konfigurovateľný zoznam) |
| Evidencia úhrady | Fakturant pri faktúre, Skladník pri platbe na mieste |
| Rozsah auditu | Každá rola vidí svoj, Supervízor vidí celý |
| Faktúry | Fakturujú sa pumpy a pokuty. Vystaviť a odoslať môže len Fakturant |
| Cena výpožičky | Zatiaľ 0 €, v konfigurácii, ukladá sa pri vydaní |
| Výber barela | Vyberá systém: najvyšší počet výpožičiek pod limitom, pri rovnosti najstarší |
| Limit výpožičiek | 10 na barel, potom sa vyradí |
| Lehota vrátenia | Koniec nasledujúceho mesiaca od dňa vydania |
| Pokuta | 10 € za nevrátený alebo poškodený barel, po zaplatení sa barel označí ako stratený |
| Mazanie | Nič sa nemaže, len mení stav a ukladá história |
| Rozsah dema (býv. Q-02) | Tenký rez, fázy 1 až 4: prihlásenie a roly, sklad barelov, objednávka, výdaj s automatickým výberom barela, vrátenie, pokuta. Pumpy, faktúry a Supervízor až potom |
| Platnosť rezervácie a horizont objednávky (býv. Q-03, 2. 10. 2026) | Rezervácia platí 3 pracovné dni od požadovaného dátumu (`reservation_validity_days`), potom ju denná úloha automaticky stornuje, kusy uvoľní a upozorní používateľa aj skladníka. Objednať možno najviac 30 dní dopredu (`order_horizon_days`) a nie do minulosti. Sviatky sa zatiaľ nezohľadňujú |
| Poškodený barel (býv. Q-04, 2. 10. 2026) | V MVP vždy odpis. Poškodený barel ide `damaged → written_off` ručne s dôvodom, oprava (`damaged → in_stock`) nie je povolená a môže prísť neskôr ako nový prechod |
| Vrátenie po lehote (býv. Q-05, 2. 10. 2026) | Pokuta za nevrátenie ostáva aj po neskorom vrátení, skladník ju môže stornovať s povinným dôvodom. Nájdený stratený barel ide `lost → in_stock`. Vrátenie peňazí za už zaplatenú pokutu sa rieši mimo systému. Dlžníkom sa človek stáva, keď denná úloha označí výpožičku po lehote alebo kým má nezaplatenú pokutu |
| Pumpy (býv. Q-06, 2. 10. 2026) | V deme jeden typ pumpy, cena pri produkte, bez limitu kusov okrem voľnej zásoby (zásoba mínus rezervácie). Model `pump_products` dovolí viac typov, typ sa dá stiahnuť z ponuky (nemaže sa). Cena sa uloží k objednávke pri vydaní |
| Kto mení konfiguráciu (býv. Q-07, 2. 10. 2026) | Super admin cez oprávnenie `settings.manage`, Supervízor len číta (`settings.read`), každá zmena ide do audit logu. Oprávnenie možno neskôr dať inej role bez zásahu do kódu |
| Pomenovanie rolí (býv. Q-08, 2. 10. 2026) | V UI „Skladník" a „Supervízor". Kódy zostávajú `warehouse` a `supervisor`, názvy sú v prekladovom slovníku |
| Technológie a prostredie (býv. Q-01, 2. 10. 2026) | Možnosť A: Python 3.12 + FastAPI, Jinja2 + HTMX, PostgreSQL 16, SQLAlchemy + Alembic, pytest, uv, Ruff. Všetko v Docker Compose (`app`, `db`), demo v Docker Desktop, neskôr Linux server. Prihlásenie meno + heslo so session, pripravené na Entra ID/Google cez Authlib (OIDC). Zamietnuté: TypeScript/Next.js, .NET/Blazor. Detail v `CLAUDE.md` kap. 8 |
