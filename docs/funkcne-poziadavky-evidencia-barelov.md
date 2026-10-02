**Evidencia a výdaj barelov s vodou**

Funkčné požiadavky na aplikáciu

| **Položka**             | **Hodnota**                                                                                                                                                    |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Verzia**              | 0.2 (schválené návrhy rolí a faktúr)                                                                                                                           |
| **Dátum**               | 2\. 10. 2026                                                                                                                                                   |
| **Stav**                | Na schválenie. Zatiaľ sa nevytvára žiadny kód.                                                                                                                 |
| **Účel dokumentu**      | Podklad pre návrh a implementáciu aplikácie (demo/MVP).                                                                                                        |
| **Zmeny vo verzii 0.2** | Nové roly Fakturant a Supervízor (len čítanie), faktúry za pumpy a pokuty, cena výpožičky (predvolene 0 €), príprava na externých zákazníkov, model oprávnení. |

# 1\. Úvod a rozsah

Aplikácia slúži na evidenciu a výdaj barelov s vodou zamestnancom a na predaj púmp na čapovanie vody. Cieľom je jednoduché riešenie, ktoré dôsledne eviduje každý barel počas celého jeho života, hlavne z dôvodu hygieny a environmentálnej evidencie.

## 1.1 V rozsahu (demo/MVP)

- Päť rolí s vlastným rozhraním: Super admin, Skladník, Fakturant, Supervízor (len čítanie), Používateľ.
- Individuálna evidencia každého barela vrátane histórie a počítadla výpožičiek.
- Objednávky a výpožičky barelov, žiadosti o výnimku nad limit.
- Vrátenie, pokuty, zoznam dlžníkov.
- Kúpa púmp s evidenciou zásob a platby (zaplatené/nezaplatené).
- Faktúry za pumpy a pokuty (v deme položkový dokument). Výpožička je zadarmo, cena je nastaviteľná (predvolene 0 €).
- Supervízor: reporty a časová os objednávok pre prípad reklamácií.
- Notifikácie v aplikácii, reporty, audit log, konfigurovateľné pravidlá.

## 1.2 Mimo rozsahu (neskoršie fázy)

- Prihlasovanie cez Entra ID, Google a podobne.
- Overenie e-mailom, e-mailové notifikácie.
- Online platby (platby sa len evidujú ručne).
- Natívna mobilná aplikácia, QR kódy na baroch.
- Zákonné náležitosti faktúr (DPH, IČO/DIČ), integrácia na účtovný systém alebo fakturačné oddelenie.
- Externí zákazníci (v MVP sa na nich len pripravuje dátový model).
- Vlastný návrhár reportov (v MVP filtre a export).

Legenda priorít: M = musí byť v MVP, S = mal by byť, C = môže prísť neskôr.

# 2\. Slovník pojmov

| **Pojem**           | **Význam**                                                                                                                     |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| **Barel**           | Fyzický barel s vodou s jedinečným ID. Nikdy sa nemaže zo systému, len mení stav.                                              |
| **Pumpa**           | Pumpa na čapovanie vody. Nedá sa požičať, iba kúpiť.                                                                           |
| **Objednávka**      | Požiadavka používateľa na výpožičku barelov (počet kusov a dátum vyzdvihnutia) alebo na kúpu pumpy.                            |
| **Rezervácia**      | Rezervuje sa počet kusov, nie konkrétny barel. Konkrétne ID pridelí systém pri vydaní.                                         |
| **Výpožička**       | Záznam o jednom konkrétnom barele vydanom jednému používateľovi s termínom vrátenia.                                           |
| **Lehota vrátenia** | Koniec nasledujúceho kalendárneho mesiaca od dňa vydania.                                                                      |
| **Pokuta**          | 10 € za každý nevrátený alebo poškodený barel (hodnota je konfigurovateľná).                                                   |
| **Dlžník**          | Používateľ s výpožičkou po lehote alebo s nezaplatenou pokutou.                                                                |
| **Vyradený barel**  | Barel, ktorý dosiahol limit výpožičiek (predvolene 10). Z hygienických dôvodov sa už nepožičiava.                              |
| **Skladník**        | Prevádzková rola (Admin/Skladník/Predajca), ktorá spracúva objednávky a sklad a vie pripraviť návrh faktúry.                   |
| **Fakturant**       | Rola, ktorá skontroluje, vystaví a odošle faktúru fakturačnému oddeleniu.                                                      |
| **Supervízor**      | Rola len na čítanie. Vidí všetko, generuje reporty a dokáže spätne preukázať, ako pracovali ostatné roly.                      |
| **Faktúra**         | Doklad s položkami (pumpy, pokuty, prípadne výpožičky s nenulovou cenou). V deme len položkový dokument bez daňovej platnosti. |
| **Oprávnenie**      | Jedna konkrétna schopnosť (napr. vystaviť faktúru). Rola je zoskupenie oprávnení.                                              |

# 3\. Roly a oprávnenia

Systém má päť rolí. Rola je zoskupenie oprávnení (napr. čítanie objednávok, vystavenie faktúry), vďaka čomu sa dajú neskôr pridať ďalšie roly bez zásahu do kódu. Oprávnenia sa vždy kontrolujú na strane servera, nielen skrytím položiek v rozhraní.

| **Funkcia**                                              | **Super admin**     | **Skladník**     | **Fakturant**           | **Supervízor** | **Používateľ** |
| -------------------------------------------------------- | ------------------- | ---------------- | ----------------------- | -------------- | -------------- |
| **Správa používateľov a rolí, deaktivácia, reset hesla** | Áno                 | Nie              | Nie                     | Nie            | Nie            |
| **Zoznam používateľov**                                  | Správa              | Čítanie          | Len na faktúre          | Čítanie        | Nie            |
| **Konfigurácia pravidiel a cien**                        | Áno (návrh)         | Nie              | Nie                     | Čítanie        | Nie            |
| **Objednávky, výpožičky, pokuty**                        | Nie                 | Plný prístup     | Len podklady k faktúram | Čítanie        | Vlastné        |
| **Sklad barelov a púmp**                                 | Nie                 | Plný prístup     | Nie                     | Čítanie        | Len voľné kusy |
| **Žiadosť o výnimku (nad 5 ks)**                         | Nie                 | Schvaľuje        | Nie                     | Čítanie        | Podáva         |
| **Návrh faktúry**                                        | Nie                 | Áno              | Áno                     | Nie            | Nie            |
| **Vystavenie a odoslanie faktúry**                       | Nie                 | Nie              | Áno                     | Nie            | Nie            |
| **Evidencia úhrady**                                     | Nie                 | Platba na mieste | Úhrada faktúry          | Nie            | Nie            |
| **Reporty**                                              | Nie                 | Prevádzkové      | Fakturačné              | Všetky         | Nie            |
| **Audit log**                                            | Správa používateľov | Prevádzkový      | Fakturačný              | Celý           | Nie            |
| **Objednať/vypožičať barel, kúpiť pumpu**                | Nie                 | Nie              | Nie                     | Nie            | Áno            |

## 3.1 Pravidlá pre roly

- Kód kontroluje oprávnenie, nie názov roly. Roly sú v databáze ako číselník s priradenými oprávneniami.
- Supervízor má iba oprávnenia na čítanie. Žiadna zápisová operácia mu nesmie prejsť, ani priamym volaním servera.
- Super admin nemôže meniť vlastnú rolu a každá zmena rolí ide do audit logu. Inak by si mohol pridať rolu, ktorú nemá mať, a obísť oddelenie povinností.
- Oddelenie povinností: skladník pripraví návrh faktúry, vystaviť ju môže iba Fakturant.
- Zakázané kombinácie rolí na jednom účte (zoznam je konfigurovateľný): Skladník + Fakturant, Supervízor + Skladník, Supervízor + Fakturant. Model dovolí viac rolí na človeka, v demo sa priraďuje jedna.
- Prístupy Supervízora k reportom a exportom sa zapisujú do audit logu. Sledovanie práce kolegov treba interne oznámiť zamestnancom (mimo aplikácie).

# 4\. Biznis pravidlá

| **ID**    | **Pravidlo**                                                                                                                                                                                                                     |
| --------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **BR-01** | Pumpu nemožno požičať, iba kúpiť. Barel možno požičať.                                                                                                                                                                           |
| **BR-02** | Lehota vrátenia je koniec nasledujúceho kalendárneho mesiaca od dňa vydania. Príklady: vydanie 1. 10. a 15. 10. a 31. 10. znamená vrátenie do 30. 11.; vydanie 15. 12. znamená vrátenie do 31. 1.                                |
| **BR-03** | Termín vrátenia sa vypočíta pri vydaní a uloží k výpožičke. Neskoršia zmena pravidla neovplyvní už vydané výpožičky.                                                                                                             |
| **BR-04** | Pokuta je 10 € za každý nevrátený alebo poškodený barel. Výška je konfigurovateľná.                                                                                                                                              |
| **BR-05** | Poškodený barel pri vrátení vytvorí pokutu okamžite. Nevrátený barel vytvorí pokutu automaticky deň po uplynutí lehoty.                                                                                                          |
| **BR-06** | Po zaplatení pokuty za nevrátený barel sa barel označí ako stratený a používateľ ho už nemusí vracať.                                                                                                                            |
| **BR-07** | Jedna objednávka obsahuje max. 5 ks barelov (konfigurovateľné). Viac je možné len cez schválenú žiadosť o výnimku.                                                                                                               |
| **BR-08** | Objednávka nesmie presiahnuť počet voľných barelov (barely na sklade mínus rezervované kusy).                                                                                                                                    |
| **BR-09** | Barel sa dá požičať max. 10-krát (konfigurovateľné). Počítadlo sa zvýši pri potvrdení vydania. Po vrátení 10. výpožičky sa barel automaticky vyradí.                                                                             |
| **BR-10** | Ak sa 10. výpožička práve realizuje, používateľ ju vracia normálne. Vyradený barel nemožno vrátiť do obehu, možný je len ručný odpis s dôvodom.                                                                                  |
| **BR-11** | Barel sa nikdy nemaže. Každá zmena stavu ukladá históriu (kto, kedy, prečo, poznámka). Rovnako sa nemažú používatelia, objednávky, pokuty ani audit log. Storno je nový záznam, pôvodný ostáva.                                  |
| **BR-12** | Konkrétny barel určuje systém, skladník ho nevyberá ani nemení. Vyberie sa dostupný barel s najvyšším počtom výpožičiek pod limitom. Pri rovnosti rozhoduje najstarší dátum zaradenia do evidencie.                              |
| **BR-13** | Pri objednávke sa rezervuje len počet kusov. ID barelov sa prideľujú pri potvrdení vydania.                                                                                                                                      |
| **BR-14** | Poškodené, stratené, odpísané a vyradené barely sa nikdy nevyberú na výdaj.                                                                                                                                                      |
| **BR-15** | Dlžník nemôže vytvárať nové objednávky (konfigurovateľné, predvolene zapnuté).                                                                                                                                                   |
| **BR-16** | Strata barela vytvára pokutu rovnako ako nevrátenie. Stratený barel sa môže po nájdení vrátiť do obehu, vyradený alebo odpísaný nie.                                                                                             |
| **BR-17** | Platby sa v MVP len evidujú ručne (zaplatené/nezaplatené). Ak existuje faktúra, úhradu eviduje Fakturant, inak Skladník pri platbe na mieste. Zaplatenie pokuty za nevrátený barel vždy spúšťa BR-06.                            |
| **BR-18** | Fakturujú sa pumpy a pokuty. Výpožička barela je zatiaľ zadarmo, ale má cenu v konfigurácii (predvolene 0 €). Ak je cena vyššia ako 0, výpožička sa stane fakturovateľnou položkou. Cena platná pri vydaní sa uloží k výpožičke. |
| **BR-19** | Návrh faktúry vie vytvoriť Skladník aj Fakturant. Vystaviť a odoslať ju fakturačnému oddeleniu môže iba Fakturant.                                                                                                               |
| **BR-20** | Číslo faktúry sa pridelí až pri vystavení, číselný rad je súvislý. Vystavená faktúra sa nemení ani nemaže. Oprava ide stornom (nový záznam s odkazom na pôvodnú faktúru).                                                        |
| **BR-21** | Jedna položka (objednávka pumpy, pokuta, výpožička) môže byť naraz iba na jednej aktívnej faktúre. Po storne faktúry sa uvoľní.                                                                                                  |
| **BR-22** | Supervízor má prístup len na čítanie ku všetkému (objednávky, sklad, história, faktúry, audit) a vie generovať reporty. Nemôže nič meniť.                                                                                        |
| **BR-23** | Každý krok objednávky ukladá časovú značku a kto ho vykonal (vytvorená, požadovaný termín, pripravená, vydaná, vrátená, notifikácia odoslaná a prečítaná). Slúži ako dôkaz pri reklamácii.                                       |

# 5\. Funkčné požiadavky

## 5.1 Používatelia a prístup (US)

| **ID**       | **Požiadavka**                                                                                                                                     | **Priorita** |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ |
| **FR-US-01** | Pri prvom nasadení existuje vopred vytvorený účet Super admin (predvolený admin).                                                                  | M            |
| **FR-US-02** | Prihlásenie menom a heslom.                                                                                                                        | M            |
| **FR-US-03** | Heslá sa ukladajú iba ako bezpečný hash, nikdy v čitateľnej podobe.                                                                                | M            |
| **FR-US-04** | Super admin vie ručne vytvoriť používateľa (prihlasovacie meno, zobrazované meno, heslo, rola).                                                    | M            |
| **FR-US-05** | Super admin vie zmeniť rolu, deaktivovať alebo aktivovať účet a resetovať heslo.                                                                   | M            |
| **FR-US-06** | Deaktivovaný účet sa nemôže prihlásiť, ale jeho história ostáva zachovaná. Účty sa nemažú.                                                         | M            |
| **FR-US-07** | Super admin nevidí objednávky, výpožičky, pokuty, dlhy ani sklad.                                                                                  | M            |
| **FR-US-08** | Skladník vidí zoznam používateľov len na čítanie a nemôže meniť roly ani oprávnenia.                                                               | M            |
| **FR-US-09** | Jednoduchý registračný formulár (meno a heslo) bez overenia e-mailom. Nový účet dostane rolu Používateľ. Registráciu možno vypnúť v konfigurácii.  | S            |
| **FR-US-10** | Používateľ si vie zmeniť vlastné heslo. Pri prvom prihlásení sa vynúti zmena hesla predvoleného admina.                                            | S            |
| **FR-US-11** | Systém má päť rolí: Super admin, Skladník, Fakturant, Supervízor, Používateľ. Roly sú zoskupením oprávnení v číselníku a kontroluje sa oprávnenie. | M            |
| **FR-US-12** | Super admin nemôže meniť vlastnú rolu. Každá zmena rolí sa zapíše do audit logu.                                                                   | M            |
| **FR-US-13** | Systém odmietne zakázané kombinácie rolí na jednom účte (konfigurovateľný zoznam).                                                                 | S            |

## 5.2 Evidencia barelov (BA)

| **ID**       | **Požiadavka**                                                                                                                            | **Priorita** |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------- | ------------ |
| **FR-BA-01** | Každý barel má jedinečné ID (kód/sériové číslo), dátum zaradenia, stav a počítadlo výpožičiek.                                            | M            |
| **FR-BA-02** | Skladník vie pridať nové barely jednotlivo alebo hromadne zadaním počtu (ID vygeneruje systém).                                           | M            |
| **FR-BA-03** | Stavy barela: na sklade, vypožičaný, poškodený, stratený, odpísaný, vyradený (limit použití).                                             | M            |
| **FR-BA-04** | Zmena stavu je možná iba cez definované prechody (kap. 6) a vždy sa zapíše do histórie (kto, kedy, dôvod, poznámka, súvisiaca výpožička). | M            |
| **FR-BA-05** | Barel nie je možné vymazať ani skladníkom, ani Super adminom.                                                                             | M            |
| **FR-BA-06** | Skladník vie označiť barel ako stratený alebo odpísaný s povinným dôvodom.                                                                | M            |
| **FR-BA-07** | Skladník vie vrátiť stratený barel do obehu, ak sa našiel. Zmena sa zapíše do histórie.                                                   | S            |
| **FR-BA-08** | Počítadlo výpožičiek sa zvýši o 1 pri potvrdení vydania.                                                                                  | M            |
| **FR-BA-09** | Po vrátení barela, ktorý dosiahol limit výpožičiek, sa automaticky prepne do stavu vyradený. Limit je konfigurovateľný.                   | M            |
| **FR-BA-10** | Zobrazenie úplnej histórie jedného barela (stavy, výpožičky, používatelia, pokuty).                                                       | M            |
| **FR-BA-11** | Zoznam barelov blížiacich sa limitu (napr. 8 a 9 výpožičiek).                                                                             | S            |

## 5.3 Sklad a prehľad (SK)

| **ID**       | **Požiadavka**                                                                                                                                                          | **Priorita** |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ |
| **FR-SK-01** | Dashboard skladníka: počet voľných, vypožičaných, rezervovaných, poškodených, stratených, odpísaných a vyradených barelov, dlžníci, čakajúce žiadosti, pumpy na sklade. | M            |
| **FR-SK-02** | Voľné barely = barely v stave na sklade mínus kusy v aktívnych rezerváciách.                                                                                            | M            |
| **FR-SK-03** | Prehľad, koľko barelov je objednaných na ktorý dátum vyzdvihnutia.                                                                                                      | M            |
| **FR-SK-04** | Skladník vidí pri každej objednávke, kto si koľko kusov objednal a na aký dátum, a aktuálny stav skladu.                                                                | M            |
| **FR-SK-05** | Konfigurovateľný prah nízkeho stavu. Pri poklese pod prah dostane skladník notifikáciu.                                                                                 | M            |

## 5.4 Objednávky a výpožičky (OB)

| **ID**       | **Požiadavka**                                                                                                                                  | **Priorita** |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------- | ------------ |
| **FR-OB-01** | Používateľ vidí počet voľných barelov a púmp.                                                                                                   | M            |
| **FR-OB-02** | Používateľ vytvorí objednávku na výpožičku 1 až 5 ks s požadovaným dátumom vyzdvihnutia.                                                        | M            |
| **FR-OB-03** | Pri vytvorení objednávky systém kontroluje limit na objednávku, dostupnosť a blokáciu dlžníka.                                                  | M            |
| **FR-OB-04** | Stavy objednávky: čaká, pripravená na vyzdvihnutie, vydaná, uzavretá, stornovaná.                                                               | M            |
| **FR-OB-05** | Používateľ vie stornovať objednávku do vydania. Rezervované kusy sa uvoľnia. Storno je nový záznam.                                             | M            |
| **FR-OB-06** | Skladník potvrdí prípravu a vydanie. Pri vydaní systém pridelí konkrétne barely podľa BR-12 a zobrazí skladníkovi zoznam ID na fyzické vydanie. | M            |
| **FR-OB-07** | Skladník nemôže pridelené barely zmeniť.                                                                                                        | M            |
| **FR-OB-08** | Pri vydaní sa vypočíta a uloží termín vrátenia (BR-02).                                                                                         | M            |
| **FR-OB-09** | Pridelenie barelov prebehne v jednej transakcii, aby sa ten istý barel nemohol vydať dvom používateľom.                                         | M            |
| **FR-OB-10** | Používateľ vidí vlastné objednávky, výpožičky, termíny vrátenia a pokuty.                                                                       | M            |
| **FR-OB-11** | Skladník vidí všetky objednávky a výpožičky s filtrom (používateľ, stav, dátum).                                                                | M            |
| **FR-OB-12** | Každý krok objednávky sa ukladá s časovou značkou a údajom, kto ho vykonal (vytvorená, požadovaný termín, pripravená, vydaná, vrátená).         | M            |

## 5.5 Žiadosti o výnimku (ZV)

| **ID**       | **Požiadavka**                                                                                                                                | **Priorita** |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------- | ------------ |
| **FR-ZV-01** | Používateľ vie podať žiadosť o výpožičku viac ako 5 ks (počet, dátum, odôvodnenie).                                                           | M            |
| **FR-ZV-02** | Stavy žiadosti: čaká, schválená, zamietnutá.                                                                                                  | M            |
| **FR-ZV-03** | Skladník žiadosť schváli alebo zamietne s voliteľnou poznámkou. Používateľ dostane notifikáciu.                                               | M            |
| **FR-ZV-04** | Schválená žiadosť vytvorí objednávku s rezerváciou kusov. Ak nie je dostatok voľných kusov, schválenie sa nedokončí a skladník je upozornený. | M            |

## 5.6 Vrátenie, pokuty a dlžníci (VR)

| **ID**       | **Požiadavka**                                                                                                                                                          | **Priorita** |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ |
| **FR-VR-01** | Skladník zaeviduje vrátenie. Pri každom barele zo zoznamu pridelených výpožičke vyberie stav: v poriadku alebo poškodený.                                               | M            |
| **FR-VR-02** | Barel vrátený v poriadku sa vráti do stavu na sklade, alebo sa vyradí, ak dosiahol limit výpožičiek.                                                                    | M            |
| **FR-VR-03** | Poškodený barel prejde do stavu poškodený a vytvorí pokutu okamžite.                                                                                                    | M            |
| **FR-VR-04** | Denná automatická úloha deň po uplynutí lehoty vytvorí pokutu k nevrátenému barelu, označí výpožičku ako po lehote a používateľa ako dlžníka.                           | M            |
| **FR-VR-05** | Pokuta má stav nezaplatená, zaplatená alebo stornovaná. Zaplatenie eviduje Skladník (na mieste) alebo Fakturant (pri vyfakturovanej pokute), vrátane dátumu a poznámky. | M            |
| **FR-VR-06** | Po zaplatení pokuty za nevrátený barel sa barel automaticky označí ako stratený a výpožička sa uzavrie (BR-06). Zmena sa zapíše do histórie.                            | M            |
| **FR-VR-07** | Skladník vie pokutu stornovať s povinným dôvodom. Pôvodný záznam ostáva.                                                                                                | S            |
| **FR-VR-08** | Zoznam dlžníkov: používateľ, počet nevrátených barelov, suma nezaplatených pokút, počet dní po lehote.                                                                  | M            |
| **FR-VR-09** | Používateľ dostane upozornenie pred termínom vrátenia (predvolene 7 dní, konfigurovateľné) a po jeho uplynutí.                                                          | M            |

## 5.7 Pumpy (PU)

| **ID**       | **Požiadavka**                                                                               | **Priorita** |
| ------------ | -------------------------------------------------------------------------------------------- | ------------ |
| **FR-PU-01** | Pumpa je produkt s názvom, cenou a zásobou na sklade.                                        | M            |
| **FR-PU-02** | Používateľ vytvorí objednávku na kúpu pumpy (počet kusov). Pumpu nie je možné vypožičať.     | M            |
| **FR-PU-03** | Pri objednávke sa kusy rezervujú, pri vydaní sa odpíšu zo zásoby.                            | M            |
| **FR-PU-04** | Skladník potvrdí vydanie. Platbu eviduje Skladník (na mieste) alebo Fakturant (cez faktúru). | M            |
| **FR-PU-05** | Skladník vie pridať pumpy na sklad (príjem). Všetky pohyby zásob sa ukladajú do histórie.    | M            |
| **FR-PU-06** | Report predaných púmp za obdobie.                                                            | S            |

## 5.8 Faktúry (FA)

| **ID**       | **Požiadavka**                                                                                                       | **Priorita** |
| ------------ | -------------------------------------------------------------------------------------------------------------------- | ------------ |
| **FR-FA-01** | Faktúra obsahuje položky z objednávok púmp, z pokút a z výpožičiek barelov (len ak je cena výpožičky vyššia ako 0).  | M            |
| **FR-FA-02** | Stavy faktúry: návrh, vystavená, odoslaná fakturačnému oddeleniu, stornovaná.                                        | M            |
| **FR-FA-03** | Skladník vie vytvoriť návrh faktúry z vydanej objednávky pumpy alebo z pokuty.                                       | M            |
| **FR-FA-04** | Fakturant vie vytvoriť a upraviť návrh (pridať alebo odobrať položky), vystaviť ho a odoslať fakturačnému oddeleniu. | M            |
| **FR-FA-05** | Pri vystavení sa pridelí súvislé číslo a dokument sa zamkne.                                                         | M            |
| **FR-FA-06** | Vystavená faktúra sa nedá upraviť ani vymazať. Oprava je storno ako nový záznam s odkazom na pôvodnú faktúru.        | M            |
| **FR-FA-07** | Demo dokument faktúry: položkový výstup (PDF) s označením „DEMO, nie je daňový doklad".                              | M            |
| **FR-FA-08** | Odoslanie fakturačnému oddeleniu je v deme zmena stavu a notifikácia, bez externej integrácie.                       | M            |
| **FR-FA-09** | Jedna položka nemôže byť naraz na dvoch aktívnych faktúrach.                                                         | M            |
| **FR-FA-10** | Fakturant vidí zoznam faktúr s filtrom (stav, obdobie, zákazník) a zoznam zatiaľ nevyfakturovaných položiek.         | M            |
| **FR-FA-11** | Fakturant eviduje úhradu faktúry. Úhrada označí zahrnuté pokuty a pumpy ako zaplatené (platí BR-06).                 | S            |

## 5.9 Notifikácie (NO)

| **ID**       | **Požiadavka**                                                                                                                                    | **Priorita** |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ |
| **FR-NO-01** | Notifikácie v aplikácii (zvonček s počtom neprečítaných, označenie ako prečítané).                                                                | M            |
| **FR-NO-02** | Skladník dostáva: novú objednávku (kto, koľko, na kedy), novú žiadosť o výnimku, nízky stav skladu, nového dlžníka.                               | M            |
| **FR-NO-03** | Používateľ dostáva: potvrdenie objednávky, objednávka pripravená, výsledok žiadosti, blížiaci sa termín vrátenia, vznik pokuty, evidovanú platbu. | M            |
| **FR-NO-04** | E-mailové notifikácie.                                                                                                                            | C            |
| **FR-NO-05** | Ukladá sa čas odoslania aj prečítania každej notifikácie (podklad pre reklamácie).                                                                | M            |
| **FR-NO-06** | Fakturant dostane notifikáciu o novom návrhu faktúry.                                                                                             | S            |

## 5.10 Reporty (RE)

| **ID**       | **Požiadavka**                                                                                         | **Priorita** |
| ------------ | ------------------------------------------------------------------------------------------------------ | ------------ |
| **FR-RE-01** | Pohyb barelov za obdobie: vydané, vrátené, poškodené, stratené, odpísané, vyradené.                    | M            |
| **FR-RE-02** | Zoznam vyradených, odpísaných a stratených barelov za obdobie (podklad pre environmentálnu evidenciu). | M            |
| **FR-RE-03** | Zoznam dlžníkov a nezaplatených pokút.                                                                 | M            |
| **FR-RE-04** | Export reportov a zoznamov do CSV/Excelu.                                                              | S            |
| **FR-RE-05** | Report faktúr: počet a hodnota za obdobie podľa stavu.                                                 | S            |

## 5.11 Supervízor a reklamácie (SV)

| **ID**       | **Požiadavka**                                                                                                                                                            | **Priorita** |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ |
| **FR-SV-01** | Supervízor má prístup len na čítanie ku všetkým dátam: objednávky, výpožičky, sklad, história barelov, pokuty, faktúry, notifikácie a audit.                              | M            |
| **FR-SV-02** | Supervízor nemôže nič vytvárať ani meniť. Všetky zápisové operácie sa odmietnu na serveri.                                                                                | M            |
| **FR-SV-03** | Časová os objednávky: vytvorená, požadovaný termín, pripravená, vydaná, vrátená, notifikácie odoslané a prečítané, kto vykonal každý krok a časové rozdiely medzi krokmi. | M            |
| **FR-SV-04** | Reporty s voľným filtrom (obdobie, používateľ, zamestnanec skladu, barel, stav, typ) s možnosťou exportu.                                                                 | M            |
| **FR-SV-05** | Prehľad skladu: vek barela, počet výpožičiek, stav, história.                                                                                                             | M            |
| **FR-SV-06** | Prehľad faktúr: počet, hodnota a stav faktúr.                                                                                                                             | M            |
| **FR-SV-07** | Report práce rolí: počet spracovaných objednávok, čas od objednávky po vydanie, počet vystavených faktúr, čas od návrhu po vystavenie.                                    | S            |
| **FR-SV-08** | Prístup Supervízora k reportom a exportom sa zapisuje do audit logu.                                                                                                      | M            |

## 5.12 Audit a konfigurácia (AU, KO)

| **ID**       | **Požiadavka**                                                                                                                                                                                                                                               | **Priorita** |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------ |
| **FR-AU-01** | Audit log eviduje dôležité akcie (kto, kedy, čo, hodnoty pred a po). Audit log sa nedá upravovať ani mazať.                                                                                                                                                  | M            |
| **FR-AU-02** | Skladník vidí audit prevádzkových akcií, Fakturant fakturačných akcií, Super admin správy používateľov a rolí. Supervízor vidí celý audit.                                                                                                                   | S            |
| **FR-KO-01** | Konfigurácia (nie pevne v kóde): max. kusov na objednávku (5), výška pokuty (10 €), pravidlo lehoty, limit výpožičiek barela (10), prah nízkeho stavu, upozornenie pred termínom (7 dní), blokácia dlžníkov, zapnutie registrácie, zakázané kombinácie rolí. | M            |
| **FR-KO-02** | Zmeny konfigurácie sa zapisujú do audit logu.                                                                                                                                                                                                                | M            |
| **FR-KO-03** | Cena výpožičky barela je v konfigurácii (predvolene 0 €). Cena platná pri vydaní sa uloží k výpožičke.                                                                                                                                                       | M            |

## 5.13 Príprava na externých zákazníkov (EX)

| **ID**       | **Požiadavka**                                                                                                               | **Priorita** |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------- | ------------ |
| **FR-EX-01** | Používateľ má typ (interný/externý). V MVP existujú len interní zamestnanci, dátový model a oprávnenia s externými počítajú. | C            |
| **FR-EX-02** | Voliteľné fakturačné údaje zákazníka (názov, IČO, DIČ, adresa). Pre interných sa nevyžadujú.                                 | C            |
| **FR-EX-03** | Ceny (výpožička, pumpa) sa pri vydaní uložia do záznamu, aby neskoršia zmena cien neovplyvnila už vydané položky.            | M            |

# 6\. Životný cyklus barela

Stav „rezervovaný" sa na úrovni barela nevedie, pretože rezervuje sa len počet kusov. Rezervované kusy sa počítajú z objednávok.

| **Stav**             | **Význam**                        | **Povolené prechody**                                                       |
| -------------------- | --------------------------------- | --------------------------------------------------------------------------- |
| **Na sklade**        | Dostupný na výdaj.                | Vypožičaný, poškodený, stratený, odpísaný                                   |
| **Vypožičaný**       | Je u používateľa.                 | Na sklade, poškodený, stratený, vyradený (po vrátení pri dosiahnutí limitu) |
| **Poškodený**        | Nepožičiava sa.                   | Odpísaný (možnosť opravy je otvorená otázka)                                |
| **Stratený**         | Nevrátený alebo nenájdený.        | Na sklade (ak sa našiel), odpísaný                                          |
| **Vyradený (limit)** | Dosiahol limit výpožičiek.        | Odpísaný (iba ručný odpis s dôvodom)                                        |
| **Odpísaný**         | Konečný stav. Zostáva v histórii. | Žiadny                                                                      |

## Stavy ďalších záznamov

| **Záznam**            | **Stavy**                                                              |
| --------------------- | ---------------------------------------------------------------------- |
| **Objednávka**        | Čaká, pripravená na vyzdvihnutie, vydaná, uzavretá, stornovaná         |
| **Žiadosť o výnimku** | Čaká, schválená, zamietnutá                                            |
| **Výpožička (barel)** | Vypožičaná, vrátená v poriadku, vrátená poškodená, po lehote, stratená |
| **Pokuta**            | Nezaplatená, zaplatená, stornovaná                                     |
| **Faktúra**           | Návrh, vystavená, odoslaná fakturačnému oddeleniu, stornovaná          |

# 7\. Návrh dátového modelu

Orientačný návrh entít. Konkrétne názvy a typy sa upresnia po výbere technológie.

| **Entita**                               | **Kľúčové polia**                                                                                                                                                          |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **User**                                 | id, prihlasovacie meno (unikátne), zobrazované meno, hash hesla, typ (interný/externý), aktívny, vytvorený, voliteľné fakturačné údaje (názov, IČO, DIČ, adresa)           |
| **Role**                                 | id, kód, názov                                                                                                                                                             |
| **Permission, RolePermission, UserRole** | oprávnenie (kód, popis), priradenie oprávnení rolám, priradenie rolí používateľom                                                                                          |
| **Barrel**                               | id, kód (unikátny), stav, počet výpožičiek, dátum zaradenia                                                                                                                |
| **BarrelStatusHistory**                  | barel, pôvodný stav, nový stav, dôvod, poznámka, kto, kedy, súvisiaca výpožička                                                                                            |
| **Order**                                | id, používateľ, typ (barel/pumpa), počet, požadovaný dátum vyzdvihnutia, stav, cena a platba (pri pumpe), časové značky krokov a kto ich vykonal                           |
| **ExceptionRequest**                     | id, používateľ, počet, dátum, odôvodnenie, stav, kto rozhodol, kedy, poznámka                                                                                              |
| **Loan**                                 | id, objednávka, barel, používateľ, poradie výpožičky barela, vydané kedy a kým, termín vrátenia, vrátené kedy, stav pri vrátení, stav výpožičky, cena výpožičky pri vydaní |
| **Penalty**                              | id, používateľ, výpožička, barel, dôvod (nevrátený/poškodený/stratený), suma, stav, vytvorená, zaplatená, kto zaevidoval, dôvod storna                                     |
| **PumpProduct**                          | id, názov, cena, zásoba                                                                                                                                                    |
| **PumpStockMovement**                    | pumpa, zmena množstva, dôvod, objednávka, kto, kedy                                                                                                                        |
| **Notification**                         | id, používateľ, typ, text, odkaz na záznam, vytvorená, prečítaná                                                                                                           |
| **AuditLog**                             | id, kto, akcia, entita, id entity, hodnoty pred/po, kedy                                                                                                                   |
| **Setting**                              | kľúč, hodnota, kto zmenil, kedy                                                                                                                                            |
| **Invoice**                              | id, číslo (až pri vystavení), stav, zákazník, vystavená kedy a kým, odoslaná kedy, celková suma, odkaz na pôvodnú faktúru a dôvod (pri storne), stav úhrady                |
| **InvoiceItem**                          | faktúra, typ položky (objednávka pumpy/pokuta/výpožička), odkaz na záznam, popis, počet, jednotková cena, suma                                                             |
| **InvoiceNumberSequence**                | rok, posledné pridelené číslo (súvislý rad bez medzier)                                                                                                                    |

# 8\. Nefunkčné požiadavky

| **ID**     | **Požiadavka**                                                                                                    |
| ---------- | ----------------------------------------------------------------------------------------------------------------- |
| **NFR-01** | Webová aplikácia, použiteľná na mobile aj na počítači.                                                            |
| **NFR-02** | Rozhranie v slovenčine, texty pripravené na neskoršiu lokalizáciu.                                                |
| **NFR-03** | Kontrola oprávnení na serveri, hashovanie hesiel, ochrana pred bežnými webovými zraniteľnosťami (OWASP).          |
| **NFR-04** | Peniaze sa ukladajú presne (desatinné číslo alebo centy), nikdy ako float.                                        |
| **NFR-05** | Časové značky v UTC, termíny vrátenia ako dátum podľa pásma Europe/Bratislava.                                    |
| **NFR-06** | Pravidelná úloha (denne) na tvorbu pokút po lehote a upozornení pred termínom.                                    |
| **NFR-07** | Nič sa nemaže. Doba uchovávania záznamov sa určí po overení legislatívy (environmentálna evidencia).              |
| **NFR-08** | Demo dáta na predvedenie (ukážkoví používatelia, barely, pumpy).                                                  |
| **NFR-09** | Zálohovanie databázy pri produkčnom nasadení.                                                                     |
| **NFR-10** | Dátový model a kód nesmú predpokladať, že každý zákazník je zamestnanec firmy (príprava na externých zákazníkov). |
| **NFR-11** | Zápisové operácie sú pre Supervízora odmietnuté na úrovni servera a pokryté testami.                              |

# 9\. Otvorené otázky

Otvorené otázky sa vedú samostatne v súbore otvorene-otazky.md. Každá má návrh riešenia, fázu, pred ktorou ju treba vyriešiť, a zápis rozhodnutia. Rozhodnuté veci sa z neho premietajú späť do tohto dokumentu.

# 10\. Navrhovaný postup realizácie

| **Fáza** | **Obsah**                                                                                                               |
| -------- | ----------------------------------------------------------------------------------------------------------------------- |
| **0**    | Dokumentácia (tento dokument a CLAUDE.md). Žiadny kód.                                                                  |
| **1**    | Základ: projekt, databáza, používatelia, roly a oprávnenia (model pre všetkých 5 rolí), prihlásenie, seed Super admina. |
| **2**    | Evidencia barelov: stavy, história, pridávanie, dashboard skladu.                                                       |
| **3**    | Objednávky, rezervácie, žiadosti o výnimku, výdaj s automatickým výberom barela, časové značky krokov.                  |
| **4**    | Vrátenie, pokuty, dlžníci, denná úloha, vyradenie po limite.                                                            |
| **5**    | Pumpy: zásoby, objednávky, platby.                                                                                      |
| **6**    | Faktúry a rola Fakturant (minimálna verzia: návrh, vystavenie, odoslanie, storno).                                      |
| **7**    | Notifikácie, reporty, export, audit log.                                                                                |
| **8**    | Rola Supervízor: rozhranie len na čítanie, časová os objednávok, reporty práce rolí.                                    |
| **9**    | Doladenie, testy pravidiel, demo dáta.                                                                                  |