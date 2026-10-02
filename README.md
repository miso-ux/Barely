# Evidencia a výdaj barelov s vodou

Demo/MVP webová aplikácia na evidenciu a výdaj barelov s vodou zamestnancom a na predaj púmp. Požiadavky sú v [docs/funkcne-poziadavky-evidencia-barelov.md](docs/funkcne-poziadavky-evidencia-barelov.md), pokyny pre vývoj v [CLAUDE.md](CLAUDE.md).

## Stack

Python 3.12, FastAPI, Jinja2 + HTMX, PostgreSQL 16, SQLAlchemy + Alembic, pytest. Všetko beží v Docker Compose, lokálne stačí Docker Desktop.

## Spustenie

```sh
cp .env.example .env     # voliteľné, bez .env sa použijú demo hodnoty
docker compose up --build
```

Aplikácia beží na `http://localhost:8000`. Pri štarte sa automaticky spustia migrácie a seed demo dát.

Prehliadač databázy (voliteľne): `docker compose --profile tools up adminer`, potom `http://localhost:8080` (systém PostgreSQL, server `db`, používateľ a heslo `barely`).

## Demo účty

Všetky účty majú heslo `Demo1234!`. Sú to len demo hodnoty zo seedu, nikdy ich nepoužívajte v ostrej prevádzke.

| Prihlasovacie meno | Rola | Poznámka |
|---|---|---|
| `admin` | Super admin | Pri prvom prihlásení si musí zmeniť heslo |
| `warehouse` | Skladník | |
| `invoicing` | Fakturant | |
| `supervisor` | Supervízor | Len na čítanie |
| `user` | Používateľ | |
| `jana.novakova`, `peter.horvath` | Používateľ | Ďalší ukážkoví používatelia pre objednávky |

Seed beží pri každom štarte, ale existujúce účty nemení. Zmenené heslá teda zostávajú. Ak je evidencia prázdna, seed tiež vytvorí 30 demo barelov (`B-0001` až `B-0030`) s rôznym počtom výpožičiek a stavmi, dve čakajúce objednávky, jednu vydanú objednávku používateľa `user` a jednu žiadosť o výnimku od `jana.novakova`. Úplný reset: `docker compose down -v`.

## Demo scenár (fázy 1 až 3)

1. Prihláste sa ako `user`, na nástenke vidíte voľné barely a požičané kusy s termínom vrátenia. Vytvorte objednávku (max. 5 ks) alebo žiadosť o výnimku nad limit.
2. Prihláste sa ako `warehouse`. Zvonček ukazuje nové objednávky a žiadosti. Na `/warehouse` je prehľad skladu a vyzdvihnutí podľa dátumu. Objednávku najprv pripravte, potom vydajte. Barely vyberie systém (najviac výpožičiek pod limitom, pri rovnosti najstarší) a zobrazí ich kódy.
3. Prihláste sa ako `supervisor`, všetko vidíte, ale nič nezmeníte.
4. Prihláste sa ako `admin` (po zmene hesla) a upravte konfiguráciu, napríklad cenu výpožičky alebo limit kusov.

## Príkazy

| Úloha | Príkaz |
|---|---|
| Testy | `docker compose run --rm app pytest` |
| Migrácie | `docker compose run --rm app alembic upgrade head` |
| Nová migrácia | `docker compose run --rm app alembic revision --autogenerate -m "popis"` |
| Seed | `docker compose run --rm app python -m app.seed` |
| Denná úloha ručne | `docker compose run --rm app python -m app.jobs.daily` |
| Lint | `docker compose run --rm app ruff check .` |
| Formátovanie | `docker compose run --rm app ruff format .` |
| Reset databázy | `docker compose down -v && docker compose up` |

## Štruktúra

- `app/` aplikácia: `models/` (tabuľky), `services/` (biznis pravidlá), `routers/` (HTTP), `templates/` a `static/` (UI), `i18n/` (texty), `jobs/` (denná úloha), `migrations/` (Alembic), `seed.py`
- `tests/unit/` testy pravidiel, `tests/integration/` testy cez HTTP
- `docs/` požiadavky, otvorené otázky, záznamy rozhodnutí (`adr/`)
