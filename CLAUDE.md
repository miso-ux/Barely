# CLAUDE.md

Pokyny pre Clauda pri práci na projekte **Evidencia a výdaj barelov s vodou**.

## 1. Aktuálna fáza

**Začíname stavať demo (fáza 1).** Rozsah dema je **tenký rez**, fázy 1 až 4: prihlásenie a roly, evidencia barelov, objednávka, výdaj s automatickým výberom barela, vrátenie, pokuta. Pumpy, faktúry, Supervízor a reporty (fázy 5 až 8) prídu až potom.

**Stav (2. 10. 2026):** Krok 0 (stack, kap. 8) a Krok 1 (kostra projektu) sú hotové. **Demo (fázy 1 až 4) je implementované:** používatelia, roly, oprávnenia, prihlásenie, konfigurácia, audit, seed; evidencia barelov so stavovým automatom, históriou a dashboardom skladu; objednávky s rezerváciami, žiadosti o výnimku, výdaj s automatickým výberom barela v jednej transakcii, notifikácie zvončekom, expirácia rezervácií podľa Q-03; vrátenie (v poriadku, poškodený, stratený), vyradenie po limite, pokuty, dlžníci a ich blokácia, denná úloha s APScheduler, platby na mieste, storno pokuty. Q-04 a Q-05 sú rozhodnuté podľa návrhov. **Fáza 5 (pumpy) je hotová:** katalóg typov púmp, príjem na sklad s históriou pohybov, objednávka pumpy ako `Order` s `kind = pump`, výdaj s odpisom zásoby a zmrazenou cenou, platba na mieste uzavrie objednávku, report predaných púmp (Q-06 rozhodnutá). **Fáza 6 (faktúry) je hotová:** nevyfakturované položky (nezaplatené pokuty, vydané nezaplatené objednávky púmp, výpožičky s cenou > 0), návrh od Skladníka alebo Fakturanta, vystavenie s číslom zo zamknutej ročnej sekvencie bez medzier, odoslanie ako zmena stavu + notifikácia (Q-09, pre demo), storno vystavenej faktúry dobropisom s odkazom na pôvodnú a uvoľnením položiek, úhrada faktúry zaplatí zahrnuté pokuty (vrátane BR-06) a pumpy, PDF cez `fpdf2` s označením „DEMO, nie je daňový doklad". **Fázy 7 a 8 (reporty, export, audit, Supervízor) sú hotové:** reporty pohyb barelov s voľnými filtrami, environmentálna evidencia, prehľad skladu, dlžníci, faktúry podľa stavu, práca rolí; každý s exportom CSV (bodkočiarka, UTF-8 s BOM pre Excel); audit s filtrami a exportom; časová os objednávky s časovými rozdielmi medzi krokmi vrátane odoslania a prečítania notifikácií; prístupy držiteľa `reports.read_all` (Supervízor) k reportom a exportom idú do auditu; doplnené notifikácie (potvrdenie objednávky, nízky stav skladu raz denne). Zostáva fáza 9 (doladenie, testy, demo dáta) a otvorené otázky Q-09 až Q-12, ktoré sa týkajú ostrej prevádzky. E-mailové notifikácie (FR-NO-04, priorita C) a export do Excelu (CSV sa v Exceli otvorí) nie sú implementované.

Fáza 4 v kóde: vrátenie v `app/services/returns.py`, pokuty v `app/services/penalties.py` (suma z konfigurácie pri vzniku, unikátny čiastočný index zaručuje jednu aktívnu pokutu na výpožičku a dôvod), dlžníci v `app/services/debtors.py`, denná úloha v `app/services/loans.py` + `app/jobs/daily.py` (expirácia rezervácií, označenie po lehote s pokutou, pripomienky), scheduler v `app/main.py` (lifespan, `SCHEDULER_ENABLED`, `DAILY_JOB_HOUR`), ručné spustenie tlačidlom na `/warehouse`. Pumpy sú v `app/services/pumps.py` (katalóg, zásoby, objednávka, výdaj so zámkom na produkte, platba, report); objednávky oboch druhov zdieľajú `validate_common` v `app/services/orders.py` a router `/orders` vetví výdaj podľa `order.is_pump`. Faktúry sú v `app/services/invoices.py` (`billable_items`, `create_draft`, `issue` s `next_number` pod zámkom riadku sekvencie, `send`, `cancel` → dobropis, `record_payment` volá `penalties.record_payment` a `pumps.record_payment` s `commit=False`) a PDF v `app/services/invoice_pdf.py`. Jedna položka na jednej aktívnej faktúre stráži čiastočný unikátny index `uq_invoice_items_active_ref` (`released = false`); odobratie z návrhu položku neuvoľňuje zmazaním, ale nastaví `removed_at` a `released`. Reporty sú v `app/services/reports.py` (každý report je `Table` s preloženými stĺpcami a riadkami, rovnaké dáta pre HTML aj CSV; prístup podľa `REPORT_PERMISSIONS`), časová os v `app/services/timeline.py`. Nový report = nová funkcia v `BUILDERS` + riadok v `REPORT_PERMISSIONS` + i18n kľúče `report.<key>.title/help`.

Kľúčové miesta v kóde: oprávnenia a ich rozdelenie do rolí sú v `app/auth/permissions.py`, kontrola na endpointoch cez `require_permission(...)` v `app/auth/deps.py`, konfigurácia v `app/services/settings.py` (`DEFAULTS`), audit cez `app/services/audit.py`. Prechody stavov barela idú výhradne cez `app/services/barrel_state.py` (`transition`), ktorý zapisuje históriu aj audit a necommituje (commit robí volajúci; výdaj v `app/services/orders.py` tak beží v jednej transakcii so zámkami `FOR UPDATE SKIP LOCKED` na baroch a `FOR UPDATE OF orders` na objednávke). Dostupnosť počíta `app/services/stock.py` (na sklade mínus rezervované v `pending` a `ready`). Notifikácie sa tvoria cez `app/services/notifications.py` (`notify`, `notify_permission_holders`), text je i18n kľúč s parametrami, čas prečítania sa ukladá. Databázové triggery zakazujú DELETE na `users`, `barrels`, `barrel_status_history` a UPDATE/DELETE na `audit_log`; pri novej doménovej tabuľke pridaj trigger `reject_delete` v migrácii. Texty UI sú v `app/i18n/sk.json`. Testy bežia proti databáze `barely_test`, ktorá sa pred každým testom vyprázdni a znovu naplní seedom; test v `tests/integration/test_supervisor.py` automaticky prechádza všetky zápisové endpointy z OpenAPI schémy.

### Krok 0: voľba technológií (blokuje všetko ostatné)

1. Prečítaj tento súbor, `docs/funkcne-poziadavky-evidencia-barelov.md` a `docs/otvorene-otazky.md`.
2. Spýtaj sa používateľa: v čom sa cíti doma (jazyk, framework), čo používa firma (hlavne či ide o Microsoft prostredie kvôli neskoršiemu Entra ID) a kde demo pobeží (lokálne vo VS Code, alebo hosting).
3. Navrhni **dve** porovnateľné možnosti s krátkymi výhodami a nevýhodami, odporuč jednu a počkaj na výber. Nevyberaj stack sám.
4. Zapíš voľbu do kap. 8 vrátane príkazov a v `docs/otvorene-otazky.md` presuň Q-01 do sekcie „Rozhodnuté".

Kritériá výberu: spustenie jedným príkazom, SQL databáza s transakciami, jednoduchý seed demo dát, dobrý testovací nástroj, minimum závislostí, možnosť neskôr pridať Entra ID/Google.

### Krok 1: založenie projektu

- Po schválení stacku navrhni štruktúru repozitára (`docs/`, zdrojový kód, testy) a počkaj na súhlas.
- Založ repozitár: git, `.gitignore`, `README.md` (ako spustiť, demo účty), priečinok `docs/` s dokumentmi.
- Seed demo účtov: jeden na každú rolu (`super_admin`, `warehouse`, `invoicing`, `supervisor`, `user`). Demo heslá len v seede a README, nikdy reálne. Super admin si pri prvom prihlásení zmení heslo (FR-US-10).
- Pred implementáciou fázy 1 napíš krátky plán (tabuľky, oprávnenia, obrazovky) a počkaj na schválenie (kap. 12).

### Definícia hotovej fázy

- pravidlá danej fázy sú pokryté testami a testy prechádzajú,
- aplikácia sa spustí podľa README,
- demo dáta sú v seede,
- stručné zhrnutie pre používateľa: čo je hotové, čo sa odchýlilo od požiadaviek, čo treba rozhodnúť.

## 2. Čo projekt rieši

Jednoduchá webová aplikácia (demo/MVP) na evidenciu a výdaj barelov s vodou zamestnancom a na predaj púmp na čapovanie vody.

- Barel sa **požičiava**, musí sa vrátiť, inak pokuta.
- Pumpa sa **iba kupuje**, nepožičiava sa.
- Každý barel sa eviduje individuálne (vlastné ID a história), kvôli hygiene a environmentálnej evidencii.
- Fakturujú sa **pumpy a pokuty**. Výpožička je zatiaľ zadarmo, ale má nastaviteľnú cenu (predvolene 0 €).
- Neskôr sa môže predávať aj externým zákazníkom, preto nepredpokladaj, že každý zákazník je zamestnanec.

Podrobnosti: `docs/funkcne-poziadavky-evidencia-barelov.md` (verzia 0.2, zdroj pravdy). Ak si s dokumentom alebo týmto súborom nie si istý, **spýtaj sa**, nič si nedomýšľaj.

## 3. Komunikácia a jazyk

- S používateľom komunikuj po slovensky.
- Kód, názvy premenných, tabuliek, endpointov, commit správy a komentáre v kóde píš po anglicky.
- Texty v používateľskom rozhraní sú po slovensky a pripravené na lokalizáciu (nie natvrdo rozhádzané po kóde).
- Odpovede drž stručné. Pri väčšej zmene najprv krátky plán a počkaj na súhlas.

## 4. Roly (päť rolí)

| Rola | Kód | Čo robí |
|---|---|---|
| Super admin | `super_admin` | Vytvára používateľov ručne, mení roly, deaktivuje účty, resetuje heslá, spravuje konfiguráciu (návrh). **Nevidí** objednávky, výpožičky, pokuty, dlhy, sklad ani faktúry. |
| Skladník (Admin/Predajca) | `warehouse` | Vidí používateľov (len čítanie), objednávky, sklad, dlžníkov. Vydáva, preberá, eviduje pokuty a platby na mieste, schvaľuje výnimky, vie vytvoriť **návrh faktúry**. **Nemôže** udeľovať oprávnenia ani vystaviť faktúru. |
| Fakturant | `invoicing` | Vytvára a upravuje návrhy faktúr, **vystavuje a odosiela** ich fakturačnému oddeleniu, eviduje úhradu faktúr. Vidí len podklady k faktúram. |
| Supervízor (názov na potvrdenie) | `supervisor` | **Iba čítanie** všetkého: objednávky, sklad, história, faktúry, audit. Generuje reporty a časové osi, aby sa dalo preukázať, ako pracovali ostatné roly (reklamácie). Nemôže nič meniť. |
| Používateľ | `user` | Objednáva/požičiava barely (max. 5 ks na objednávku), žiada o výnimku nad 5 ks, kupuje pumpu, vidí len vlastné veci. |

**Roly sú zoskupenia oprávnení.** Kód kontroluje oprávnenie (napr. `orders.read_all`, `invoices.issue`, `reports.read_all`), nikdy názov roly. Roly aj oprávnenia sú v databáze (`Role`, `Permission`, `RolePermission`, `UserRole`). Presný zoznam oprávnení navrhni pri fáze 1 a daj na schválenie.

Pravidlá rolí:

- Oprávnenia sa kontrolujú **na serveri**, nie len skrytím v UI.
- Supervízor má len oprávnenia na čítanie. Každá zápisová operácia musí pre neho vrátiť zamietnutie.
- Super admin **nemôže meniť vlastnú rolu**. Každá zmena rolí ide do audit logu.
- Zakázané kombinácie rolí na jednom účte (schválené, konfigurovateľný zoznam): `warehouse` + `invoicing`, `supervisor` + `warehouse`, `supervisor` + `invoicing`. Model dovolí viac rolí na človeka, v demo sa priraďuje jedna.

Super admin je predvolený účet vytvorený pri prvom nasadení (seed). Prihlasovanie je meno + heslo, bez e-mailového overenia. Voliteľne jednoduchý registračný formulár (nový účet = `user`). Entra ID/Google až neskôr, preto auth rieš tak, aby sa dal neskôr vymeniť.

## 5. Biznis pravidlá (skratka, detail v dokumente)

1. **Lehota vrátenia** = koniec nasledujúceho kalendárneho mesiaca od dňa vydania. Vydanie 1. 10., 15. 10. aj 31. 10. → 30. 11. Vydanie 15. 12. → 31. 1. Termín sa vypočíta pri vydaní a uloží; zmena pravidla nemení už vydané výpožičky.
2. **Pokuta 10 €** za každý nevrátený alebo poškodený barel (konfigurovateľné). Poškodený → pokuta hneď pri vrátení. Nevrátený → automaticky deň po lehote.
3. Po **zaplatení pokuty za nevrátený barel** sa barel označí ako `lost` a používateľ ho už nemusí vracať.
4. **Max. 5 ks na objednávku** (konfigurovateľné). Viac len cez **žiadosť o výnimku** schválenú skladníkom.
5. Objednávka nesmie presiahnuť **voľné** barely = barely `in_stock` mínus rezervované kusy.
6. **Limit 10 výpožičiek** na barel (konfigurovateľné). Počítadlo +1 pri **potvrdení vydania**. Po vrátení 10. výpožičky sa barel automaticky stane `retired`. Vyradený barel sa nevracia do obehu, iba ručný odpis (`written_off`) s dôvodom.
7. **Systém vyberá barel, nie skladník.** Pri objednávke sa rezervuje len počet kusov. Pri vydaní sa vyberie dostupný barel s **najvyšším počtom výpožičiek pod limitom**; pri rovnosti najstarší podľa dátumu zaradenia. Skladník dostane zoznam pridelených ID a nemôže ich meniť.
8. `damaged`, `lost`, `written_off`, `retired` barely sa nikdy nevyberú na výdaj.
9. **Dlžník** = používateľ s výpožičkou po lehote alebo nezaplatenou pokutou. Dlžník nemôže vytvárať nové objednávky (konfigurovateľné, predvolene zapnuté).
10. **Nič sa nemaže.** Barely, používatelia, objednávky, pokuty ani audit log sa nikdy nemažú (žiadny hard delete). Storno je nový záznam, pôvodný ostáva. Kvôli environmentálnej evidencii.
11. Platby sa len evidujú ručne (zaplatené/nezaplatené). Ak existuje faktúra, úhradu eviduje Fakturant, inak Skladník pri platbe na mieste. Zaplatenie pokuty za nevrátený barel vždy spúšťa pravidlo 3. Online platby sú mimo rozsahu.
12. **Fakturujú sa pumpy a pokuty.** Výpožička má cenu v konfigurácii (`loan_price`, predvolene 0 €). Ak je cena > 0, výpožička je fakturovateľná položka. Cena platná pri vydaní sa uloží k výpožičke (rovnako ako `due_date`). Rovnako sa pri vydaní ukladá cena pumpy.
13. Návrh faktúry vie vytvoriť Skladník aj Fakturant. **Vystaviť a odoslať ju vie len Fakturant.**
14. Číslo faktúry sa pridelí **až pri vystavení**, číselný rad je súvislý bez medzier. Vystavená faktúra sa nemení ani nemaže, oprava je storno (nový záznam s odkazom na pôvodnú). V deme je faktúra len položkový PDF dokument s označením „DEMO, nie je daňový doklad".
15. Jedna položka (objednávka pumpy, pokuta, výpožička) môže byť naraz len na jednej aktívnej faktúre. Po storne sa uvoľní.
16. **Časové značky:** každý krok objednávky ukladá čas a kto ho vykonal (vytvorená, požadovaný termín, pripravená, vydaná, vrátená, notifikácia odoslaná a prečítaná). Supervízor z nich skladá časovú os pri reklamáciách.
17. Prístupy Supervízora k reportom a exportom sa zapisujú do audit logu.

## 6. Stavy barela

`in_stock`, `on_loan`, `damaged`, `lost`, `retired` (limit), `written_off` (konečný).

Povolené prechody:

- `in_stock` → `on_loan`, `damaged`, `lost`, `written_off`
- `on_loan` → `in_stock`, `damaged`, `lost`, `retired`
- `damaged` → `written_off`
- `lost` → `in_stock` (ak sa našiel), `written_off`
- `retired` → `written_off`
- `written_off` → nič

Každý prechod ide cez **jedno miesto v kóde** (state machine) a zapíše históriu: kto, kedy, dôvod, poznámka, súvisiaca výpožička. „Rezervovaný" nie je stav barela, rezervácie sú počty kusov v objednávkach.

Ďalšie stavy: objednávka (`pending`, `ready`, `issued`, `closed`, `cancelled`), žiadosť o výnimku (`pending`, `approved`, `rejected`), pokuta (`unpaid`, `paid`, `cancelled`), faktúra (`draft`, `issued`, `sent`, `cancelled`).

## 7. Doménový model (skratka)

`User` (typ interný/externý, voliteľné fakturačné údaje), `Role`, `Permission`, `RolePermission`, `UserRole`, `Barrel`, `BarrelStatusHistory`, `Order`, `ExceptionRequest`, `Loan` (jeden barel jednému používateľovi s `due_date` a cenou pri vydaní), `Penalty`, `PumpProduct`, `PumpStockMovement`, `Invoice`, `InvoiceItem`, `InvoiceNumberSequence`, `Notification`, `AuditLog`, `Setting`. Polia sú v kap. 7 dokumentu.

## 8. Technológie

**Rozhodnuté 2. 10. 2026** (Q-01, možnosť A). Lokálne nie je nainštalovaný žiadny runtime, iba Docker Desktop. Všetko beží v kontajneroch, vývoj aj testy.

| Vrstva | Voľba |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 (ORM), Alembic (migrácie), Pydantic |
| Frontend | Serverovo renderované Jinja2 šablóny + HTMX pre dynamické časti, Pico CSS (responzívne, mobil aj počítač). Texty UI v slovenčine cez prekladové slovníky, nie natvrdo v šablónach. |
| Databáza | PostgreSQL 16 (transakcie, `SELECT ... FOR UPDATE` pri prideľovaní barelov a číslovaní faktúr) |
| Autentifikácia | meno + heslo, session cookie, hash hesiel cez Argon2 (`pwdlib`). Prihlásenie je oddelená vrstva, aby sa neskôr dal pridať Entra ID/Google cez Authlib (OIDC). |
| Testy | pytest, testy biznis pravidiel bežia proti PostgreSQL v kontajneri |
| Denná úloha | APScheduler v procese aplikácie, plus ručné spustenie cez CLI príkaz (na demo a testy) |
| Nasadenie | Docker Compose: kontajner `app` (FastAPI cez Uvicorn) a `db` (PostgreSQL), voliteľne `adminer`. Demo beží v Docker Desktop, produkcia neskôr na Linux serveri. |
| Správa závislostí | `uv` (lock súbor `uv.lock`), `pyproject.toml` |
| Lint | Ruff (lint aj formátovanie) |

Dôvody výberu: minimum závislostí, stabilné knižnice s nebolestivými upgradmi, jednoduché unit testy pravidiel bez prehliadača, jeden kontajner pre aplikáciu, malý image. Zamietnuté: TypeScript/Next.js (viac závislostí, rýchle zmeny frameworku) a .NET/Blazor (ťažký rozbeh pre demo).

### Príkazy

Všetko sa spúšťa cez Docker Compose z koreňa repozitára.

| Úloha | Príkaz |
|---|---|
| Inštalácia závislostí | `docker compose build` (závislosti sa inštalujú do image cez `uv sync`) |
| Spustenie aplikácie | `docker compose up` (aplikácia na `http://localhost:8000`, pri štarte sa spustia migrácie a seed, ak je databáza prázdna) |
| Testy | `docker compose run --rm app pytest` |
| Migrácie databázy | `docker compose run --rm app alembic upgrade head`; nová migrácia: `docker compose run --rm app alembic revision --autogenerate -m "popis"` |
| Naplnenie demo dátami (seed) | `docker compose run --rm app python -m app.seed` |
| Denná úloha ručne | `docker compose run --rm app python -m app.jobs.daily` |
| Lint a formátovanie | `docker compose run --rm app ruff check .` a `docker compose run --rm app ruff format .` |
| Reset databázy (len demo) | `docker compose down -v` a potom `docker compose up` |

## 9. Technické zásady (platia pre akýkoľvek stack)

- **Žiadny hard delete** nad doménovými dátami. Používatelia sa deaktivujú, záznamy sa stornujú.
- **Konfigurácia v databáze** (tabuľka `Setting`), nie pevne v kóde: max. kusov na objednávku (5), pokuta (10 €), limit výpožičiek (10), prah nízkeho stavu, upozornenie pred termínom (7 dní), blokácia dlžníkov, zapnutie registrácie, cena výpožičky (`loan_price`, 0 €), zakázané kombinácie rolí.
- **Peniaze** presne (decimal alebo centy), nikdy float.
- **Čas:** časové značky v UTC, `due_date` ako dátum v pásme Europe/Bratislava.
- **Pridelenie barelov pri vydaní v jednej transakcii** so zámkom, aby sa jeden barel nevydal dvom ľuďom.
- **Autorizácia na serveri** pri každom endpointe podľa oprávnení, nie len skrytie tlačidiel.
- **Neexistuje pevná väzba na zamestnancov.** Zákazník je `User` s typom. Pripravuj kód tak, aby sa dali neskôr pridať externí zákazníci (fakturačné údaje, schvaľovanie registrácie).
- **Ceny sa ukladajú pri vydaní** do záznamu, nikdy sa nepočítajú spätne z aktuálnej konfigurácie.
- **Audit log** pre dôležité akcie (kto, kedy, čo, pred/po). Nedá sa upraviť ani zmazať.
- **Denná úloha:** pokuty po lehote, upozornenia pred termínom, označenie dlžníkov.
- **Notifikácie v aplikácii** (zvonček). E-mail až neskôr.
- Hesla nikdy v čitateľnej podobe, žiadne tajomstvá v repozitári.

## 10. Testy

Pravidlá z kap. 5 pokry unit testami skôr než UI, hlavne:

- výpočet termínu vrátenia (1. 10. → 30. 11., 31. 10. → 30. 11., 15. 12. → 31. 1.),
- výber barela (najvyšší počet výpožičiek pod limitom, pri rovnosti najstarší),
- limit 10 výpožičiek a vyradenie po vrátení,
- limit 5 ks, dostupnosť, blokácia dlžníka,
- vznik pokút (poškodený, po lehote) a prechod na `lost` po zaplatení,
- zákaz mazania a povolené prechody stavov,
- Supervízor: každý zápisový endpoint vráti zamietnutie, čítanie funguje,
- Super admin nemôže zmeniť vlastnú rolu, zakázané kombinácie rolí sa odmietnu,
- faktúry: číslo až pri vystavení, súvislý rad, vystavená faktúra sa nedá zmeniť, storno uvoľní položky, položka nie je na dvoch aktívnych faktúrach,
- cena výpožičky 0 € nevytvorí fakturovateľnú položku, cena > 0 áno a uloží sa pri vydaní.

## 11. Plán fáz

0. Dokumentácia (hotovo).
1. Základ: projekt, databáza, používatelia, roly a oprávnenia (model pre všetkých 5 rolí), prihlásenie, seed Super admina.
2. Evidencia barelov: stavy, história, pridávanie, dashboard skladu.
3. Objednávky, rezervácie, žiadosti o výnimku, výdaj s automatickým výberom barela, časové značky krokov, základná notifikácia skladníkovi o novej objednávke (zvonček).
4. Vrátenie, pokuty, dlžníci, denná úloha, vyradenie po limite.
5. Pumpy: zásoby, objednávky, platby.
6. Faktúry a rola Fakturant (minimálna verzia: návrh, vystavenie, odoslanie, storno).
7. Ostatné notifikácie, reporty, export CSV/Excel, audit log.
8. Rola Supervízor: rozhranie len na čítanie, časová os objednávok, reporty práce rolí.
9. Doladenie, testy, demo dáta.

**Demo (tenký rez) = fázy 1 až 4.**

Pred fázou 3 potvrď s používateľom otázku Q-03 a pred fázou 4 otázky Q-04 a Q-05. Každá má v `docs/otvorene-otazky.md` návrh. Ukáž ho a nechaj potvrdiť, nehádaj.

Pracuj fázu po fáze, v malých commitoch (správy po anglicky). Pred prechodom na ďalšiu fázu zhrň, čo je hotové.

## 12. Pracovná dohoda

- Nevymýšľaj pravidlá. Ak niečo chýba alebo si protirečí, spýtaj sa a pridaj to do otvorených otázok.
- Pri zmene požiadaviek aktualizuj dokument aj tento súbor.
- Pred väčšou zmenou (nová tabuľka, zmena stavov, nová závislosť) navrhni plán a počkaj na súhlas.
- Nerob refaktoring mimo zadania.

## 13. Otvorené otázky

Vedú sa samostatne v `docs/otvorene-otazky.md` (každá s návrhom a fázou, pred ktorou ju treba vyriešiť). Ak otázka blokuje prácu, nehádaj, spýtaj sa. Po rozhodnutí ju presuň do sekcie „Rozhodnuté" a premietni do požiadaviek a tohto súboru.
