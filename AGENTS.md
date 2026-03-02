# AGENTS.md — CenyPradu

Kontekst dla agentów AI (Claude Code, Codex, itp.) pracujących z tym repozytorium.

## Opis projektu

Automatyczne pobieranie godzinowych cen energii elektrycznej z TGE (Towarowa Giełda Energii, Fixing I, Rynek Dnia Następnego) i udostępnianie ich jako statyczne pliki JSON przez GitHub Pages. Katalog taryf dystrybucyjnych OSD + kalkulator kosztów. Frontend w planach.

## Stan realizacji

- **Faza 1 (Scraper + CI):** gotowe — `scripts/scrape_tge.py`, GitHub Actions cron
- **Faza 2 (Taryfy):** gotowe — 17 plików JSON w `data/tariffs/`, kalkulator `web/js/tariffs.js`
- **Faza 3 (Frontend):** nie zaczęte — brak `index.html`, `app.js`, `chart.js`

## Struktura

```
scripts/
  scrape_tge.py           Python scraper (requests + BeautifulSoup + lxml)
  requirements.txt        Zależności Python
.github/workflows/
  scrape-prices.yml       Cron 10:00 UTC, workflow_dispatch z delivery_date
data/prices/
  index.json              Indeks dostępnych dat {"dates": [...], "latest": "..."}
  YYYY-MM-DD.json         Ceny godzinowe Fixing I
data/tariffs/
  schema.json             JSON Schema Draft 2020-12
  operator-grupa.json     17 taryf (tauron/energa/enea/pge/stoen × G11/G12/G12w/G13...)
web/js/
  tariffs.js              Kalkulator kosztów (flat, tou, seasonal)
  holidays.js             Polskie święta (stałe + ruchome wg Wielkanocy)
docs/
  architecture.md         Architektura systemu
  task-1-scraper.md       Specyfikacja scrapera (uaktualniona)
  task-2-tariffs.md       Specyfikacja taryf
  task-3-frontend.md      Specyfikacja frontendu
```

## Scraper — jak działa

1. URL: `https://tge.pl/energia-elektryczna-rdn?dateShow=DD-MM-YYYY`
   - `dateShow` = delivery_date − 1 dzień
2. Pobiera HTML przez `requests` z nagłówkami Chrome
3. Parsuje tabelę `#rdn > tbody` — wiersze godzinowe (`_H01`–`_H24`), pomija 15-min (`_Q`)
4. Cena Fixing I: `td[2]`, format polski (`312,50`)
5. Buduje timestampy z UTC offset (Europe/Warsaw, obsługa DST 23/24/25h)
6. Waliduje: 23–25 godzin, ceny w zakresie −500–10 000 PLN/MWh
7. Zapisuje do `data/prices/YYYY-MM-DD.json` + aktualizuje `index.json`

CLI: `python scripts/scrape_tge.py [YYYY-MM-DD] [--force] [--verify]`

## Formaty danych

### Ceny (`data/prices/YYYY-MM-DD.json`)

```json
{
  "date": "2026-03-02",
  "scraped_at": "2026-03-01T10:05:22Z",
  "unit": "PLN/MWh",
  "prices": [
    {"time": "2026-03-02 00:00:00+01:00", "price": 364.6},
    {"time": "2026-03-02 01:00:00+01:00", "price": 340.2}
  ]
}
```

- `time` = początek godziny dostawy, ISO 8601 z offset (`+01:00` CET, `+02:00` CEST)
- Zwykle 24 elementów; 23 przy spring-forward, 25 przy fall-back

### Taryfy (`data/tariffs/operator-grupa.json`)

Typy stawek zmiennych (`variable_rates_pln_kwh.type`):
- `flat` — jedna stawka (G11)
- `tou` — strefy czasowe (G12, G12w)
- `tou` + `seasonal: true` — sezonowe z harmonogramem miesięcznym (G13, G13s, G13active)

Harmonogram stref: `"HH:MM-HH:MM"` (czas lokalny), typy dni: `weekday`/`saturday`/`sunday`/`holiday`.

## Konwencje kodowania

- **Język:** polski (komentarze, docstringi, logi, UI, commity)
- **Python:** snake_case, type hints (3.12+), logi na stderr, `argparse` dla CLI
- **JavaScript:** camelCase, ES2022 modules, vanilla (bez frameworków/bundlerów)
- **Nazwy plików:** snake_case (Python), kebab-case (taryfy JSON)
- **Frontend:** vanilla HTML/CSS/JS, Tailwind CDN, Chart.js CDN, brak npm/webpack

## GitHub Actions

Workflow `scrape-prices.yml`:
- Trigger: cron `0 10 * * *` (11:00 CET / 12:00 CEST) + `workflow_dispatch`
- Input: `delivery_date` (YYYY-MM-DD, opcjonalny)
- Kroki: checkout → Python 3.12 → pip install → `scrape_tge.py` → git commit+push
- Commit msg: `data: ceny TGE Fixing I dla YYYY-MM-DD`

## Uwagi

- Scraper używa `requests` (nie Playwright) — TGE nie wymaga renderowania JS
- Taryfy zmieniane ręcznie (zatwierdzane przez URE, aktualizacja ~raz/rok)
- `scraped_webpage.html` w root to artefakt debugowy, nie część systemu
