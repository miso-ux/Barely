# Otvorené otázky

Projekt: Evidencia a výdaj barelov s vodou. Stav k 2. 10. 2026. Q-01, Q-02, Q-07 a Q-08 sú vyriešené (ID sa nepoužíva znova).
Súvisiace dokumenty: `funkcne-poziadavky-evidencia-barelov.md` (v0.2), `CLAUDE.md`.

## Ako s týmto súborom pracovať

- Každá otázka má **návrh**. Ak sa nerozhodneme inak, platí návrh.
- Po rozhodnutí sa otázka presunie do sekcie **Rozhodnuté** a premietne sa do požiadaviek a `CLAUDE.md`.
- Ak otázka blokuje prácu na danej fáze, Claude nehádaj. Spýta sa.

## Prehľad

| ID | Téma | Treba vyriešiť pred | Blokuje? |
|---|---|---|---|
| Q-03 | Platnosť rezervácie a horizont objednávky | Fáza 3 | Čiastočne |
| Q-04 | Poškodený barel: oprava alebo odpis | Fáza 4 | Nie, návrh stačí |
| Q-05 | Vrátenie po lehote pred zaplatením pokuty | Fáza 4 | Nie, návrh stačí |
| Q-06 | Pumpy: typy, cena, limity | Fáza 5 | Čiastočne |
| Q-09 | Odovzdanie faktúry a jej náležitosti | Fáza 6 | Nie pre demo |
| Q-10 | Uchovávanie záznamov a GDPR | Pred ostrým nasadením | Nie pre demo |
| Q-11 | Externí zákazníci | Pred ich spustením | Nie pre demo |
| Q-12 | Informovanie zamestnancov o Supervízorovi | Pred fázou 8 | Nie pre demo |

---

## Q-03 Platnosť rezervácie a horizont objednávky

**Otázka:** Ako dlho platí rezervácia, ak sa používateľ nedostaví na vyzdvihnutie? Ako ďaleko dopredu možno objednať?

**Prečo na tom záleží:** Rezervované kusy sa počítajú do dostupnosti. Bez limitu by neprevzaté objednávky blokovali sklad.

**Návrh:** Rezervácia platí 3 pracovné dni od požadovaného dátumu, potom sa automaticky stornuje, kusy sa uvoľnia a skladník dostane notifikáciu. Objednať sa dá najviac 30 dní dopredu a nie do minulosti. Oba limity budú v konfigurácii.

**Rozhodnutie:** zatiaľ nie

---

## Q-04 Poškodený barel: oprava alebo odpis

**Otázka:** Dá sa poškodený barel opraviť a vrátiť do obehu, alebo sa vždy odpisuje?

**Prečo na tom záleží:** Mení povolené prechody stavov (`damaged` → `in_stock`) a hygienické pravidlá.

**Návrh:** V MVP vždy odpis, je to jednoduchšie a hygienicky bezpečnejšie. Oprava môže prísť neskôr ako nový prechod s povinným dôvodom.

**Rozhodnutie:** zatiaľ nie

---

## Q-05 Vrátenie po lehote pred zaplatením pokuty

**Otázka:** Čo sa stane, ak používateľ vráti barel po lehote, ale pokuta ešte nie je zaplatená? A čo ak je pokuta už zaplatená a barel sa označil ako stratený?

**Prečo na tom záleží:** Okrajové prípady, ktoré sa v prevádzke určite objavia a majú finančný dopad.

**Návrh:** Pokuta ostáva, lebo vznikla porušením lehoty. Skladník ju môže stornovať s povinným dôvodom. Vrátený barel sa vráti do obehu (`lost` → `in_stock`). Ak už bola pokuta zaplatená, vrátenie peňazí sa rieši mimo systému alebo dobropisom k faktúre.

**Rozhodnutie:** zatiaľ nie

---

## Q-06 Pumpy: typy, cena, limity

**Otázka:** Koľko typov púmp bude, aká je cena a je limit kusov na jednu objednávku?

**Prečo na tom záleží:** Určuje tvar katalógu a objednávky pumpy.

**Návrh:** Jeden typ pumpy, cena uložená pri produkte, bez limitu okrem aktuálnej zásoby. Dátový model necháme tak, aby šlo neskôr pridať viac typov.

**Rozhodnutie:** zatiaľ nie

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
| Kto mení konfiguráciu (býv. Q-07, 2. 10. 2026) | Super admin cez oprávnenie `settings.manage`, Supervízor len číta (`settings.read`), každá zmena ide do audit logu. Oprávnenie možno neskôr dať inej role bez zásahu do kódu |
| Pomenovanie rolí (býv. Q-08, 2. 10. 2026) | V UI „Skladník" a „Supervízor". Kódy zostávajú `warehouse` a `supervisor`, názvy sú v prekladovom slovníku |
| Technológie a prostredie (býv. Q-01, 2. 10. 2026) | Možnosť A: Python 3.12 + FastAPI, Jinja2 + HTMX, PostgreSQL 16, SQLAlchemy + Alembic, pytest, uv, Ruff. Všetko v Docker Compose (`app`, `db`), demo v Docker Desktop, neskôr Linux server. Prihlásenie meno + heslo so session, pripravené na Entra ID/Google cez Authlib (OIDC). Zamietnuté: TypeScript/Next.js, .NET/Blazor. Detail v `CLAUDE.md` kap. 8 |
