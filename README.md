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

Doplnia sa vo fáze 1 (jeden účet na každú rolu). Heslá sú len demo, Super admin si ich pri prvom prihlásení musí zmeniť.

## Príkazy

| Úloha | Príkaz |
|---|---|
| Testy | `docker compose run --rm app pytest` |
| Migrácie | `docker compose run --rm app alembic upgrade head` |
| Nová migrácia | `docker compose run --rm app alembic revision --autogenerate -m "popis"` |
| Seed | `docker compose run --rm app python -m app.seed` |
| Lint | `docker compose run --rm app ruff check .` |
| Formátovanie | `docker compose run --rm app ruff format .` |
| Reset databázy | `docker compose down -v && docker compose up` |

## Štruktúra

- `app/` aplikácia: `models/` (tabuľky), `services/` (biznis pravidlá), `routers/` (HTTP), `templates/` a `static/` (UI), `i18n/` (texty), `jobs/` (denná úloha), `migrations/` (Alembic), `seed.py`
- `tests/unit/` testy pravidiel, `tests/integration/` testy cez HTTP
- `docs/` požiadavky, otvorené otázky, záznamy rozhodnutí (`adr/`)
