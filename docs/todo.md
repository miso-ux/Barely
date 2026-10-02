# To Do: odložené témy

Veci, ktoré demo zámerne nerieši. Každá má krátky návrh, kde v kóde začať.

| Téma | Stav | Návrh |
|---|---|---|
| Prihlásenie cez Entra ID / Google | Odložené | Pridať Authlib (OIDC). Po úspešnom externom prihlásení zavolať `login_user` v `app/auth/deps.py` a spárovať účet podľa e-mailu alebo `sub`. Meno + heslo ponechať ako záložný spôsob. Nový stĺpec `users.external_id`. |
| CSRF token vo formulároch | Odložené | Dnes stojí ochrana na `SameSite=Lax` cookie. Pridať podpísaný token do session, hidden input do každého formulára (`base.html` macro) a kontrolu v middleware pre POST. |
| E-mailové notifikácie (FR-NO-04) | Odložené, priorita C | Notifikácie už vznikajú v `app/services/notifications.py`; doplniť odosielanie e-mailu (SMTP nastavenia v `.env`) pri vybraných typoch a voľbu používateľa, či ich chce. |
| Export do Excelu (XLSX) | Odložené | CSV z `app/services/reports.py` sa v Exceli otvorí (bodkočiarka, UTF-8 s BOM). Ak bude treba natívny XLSX, pridať `openpyxl` a druhý výstup `Table.xlsx()`. |
| Sviatky pri expirácii rezervácie | Odložené | `app/services/dates.py` ráta pracovné dni len Po až Pia. Pridať zoznam sviatkov do konfigurácie (`settings`) a zohľadniť ho v `add_working_days`. |
| Upozornenie na nízky stav púmp | Odložené | `stock.notify_low_stock` rieši len barely. Pridať prah pre pumpy a obdobnú notifikáciu. |
| Náležitosti faktúr a odovzdanie (Q-09) | Otvorené | Overiť s účtovníctvom. Dátový model má miesto pre fakturačné údaje zákazníka (`users.billing_*`); doplniť DPH, splatnosť, číslovanie podľa účtovného systému a spôsob odovzdania (e-mail, export). |
| Uchovávanie záznamov a GDPR (Q-10) | Otvorené | Overiť s právnikom. Technicky: anonymizácia osobných údajov deaktivovaného používateľa po lehote, záznamy o baroch ostávajú. |
| Externí zákazníci (Q-11) | Otvorené | Schvaľovanie registrácie, overenie e-mailom, cenník, DPH, online platby. `users.customer_type` a fakturačné údaje už existujú. |
| Informovanie zamestnancov o Supervízorovi (Q-12) | Otvorené | Interná smernica pred nasadením roly, mimo aplikácie. |
| Oprava poškodeného barela (Q-04, neskôr) | Odložené | Nový prechod `damaged → in_stock` s povinným dôvodom v `app/services/barrel_state.py`, test matice prechodov upraviť. |
| Produkčné nasadenie | Odložené | `SECURE_COOKIES=true`, `FORWARDED_ALLOW_IPS` na adresu proxy, silný `SECRET_KEY`, zálohy PostgreSQL (NFR-09), `APP_ENV=production` (bez `--reload`). |
