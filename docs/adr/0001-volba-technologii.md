# ADR 0001: Voľba technológií

Dátum: 2. 10. 2026. Stav: prijaté (otázka Q-01).

## Kontext

Demo/MVP na evidenciu a výdaj barelov. Kritériá: spustenie jedným príkazom, SQL databáza s transakciami a zámkami, jednoduchý seed, dobré testy biznis pravidiel, minimum závislostí, neskoršie Entra ID/Google. Používateľ nemá lokálne žiadny runtime, len Docker Desktop. Cieľové prostredie je Linux server s kontajnermi.

## Zvažované možnosti

- **A: Python, FastAPI + Jinja2/HTMX, PostgreSQL.** Málo závislostí, stabilné knižnice, testy pravidiel bez prehliadača, jeden kontajner pre aplikáciu. Jednoduchšie UI.
- **B: TypeScript, Next.js + Prisma, PostgreSQL.** Jeden jazyk end-to-end, moderné UI. Viac závislostí, rýchle zmeny frameworku, zámky cez raw SQL.
- **.NET 8 + Blazor.** Najlepšia Entra ID integrácia, ale ťažký rozbeh a veľký image pre demo.

## Rozhodnutie

Možnosť A. Detail stacku a príkazov je v `CLAUDE.md` kap. 8.

## Dôsledky

- Biznis pravidlá sú v `app/services/`, UI vrstva sa dá neskôr vymeniť.
- Autentifikácia je oddelená vrstva, Entra ID/Google sa doplní cez Authlib (OIDC) bez zásahu do zvyšku.
- Všetko (vývoj, testy, migrácie, seed) beží cez Docker Compose, lokálne netreba Python.
