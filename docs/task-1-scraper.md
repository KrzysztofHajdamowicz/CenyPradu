# Zadanie 1: Scraper TGE + GitHub Actions + GitHub Pages

## Cel

Codzienne automatyczne pobieranie godzinowych cen energii elektrycznej (Fixing I) z TGE, zapisywanie ich jako pliki JSON w repozytorium i udostępnianie przez GitHub Pages.

## Status: Gotowe

Scraper działa od 2026-01-01. Dane zbierane codziennie przez GitHub Actions.

---

## Efekt końcowy

1. GitHub Actions uruchamia się codziennie o 11:00 CET (cron `0 10 * * *` UTC)
2. Skrypt scrapuje `https://tge.pl/energia-elektryczna-rdn?dateShow=DD-MM-YYYY`
3. Pobrane ceny zapisywane są jako `data/prices/YYYY-MM-DD.json`
4. `data/prices/index.json` jest aktualizowany
5. Zmiany są commitowane i pushowane do gałęzi `main`
6. Pliki JSON dostępne publicznie przez GitHub Pages

---

## Pliki

```
scripts/
  scrape_tge.py               # Scraper Python (requests + BeautifulSoup)
  requirements.txt            # Zależności
.github/workflows/
  scrape-prices.yml           # Harmonogram + CI
data/prices/
  index.json                  # Indeks dostępnych dat
  YYYY-MM-DD.json             # Ceny godzinowe
```

---

## Źródło danych

**URL:** `https://tge.pl/energia-elektryczna-rdn?dateShow=DD-MM-YYYY`

Parametr `dateShow` to data *przeglądania* (delivery_date − 1 dzień), nie data dostawy.

### Struktura HTML

```
Tabela: #rdn > tbody
Wiersze godzinowe: td[0]="2026-02-28_H01", td[1]="60", td[2]=cena Fixing I
Wiersze 15-min:    td[0]="2026-02-28_Q00:15", td[1]="15" — pomijane
Nagłówek daty:     .kontrakt-date > small ("dla dostawy w dniu DD-MM-YYYY")
```

### Podejście: requests + BeautifulSoup

Strona TGE renderuje tabelę server-side — nie wymaga JavaScript. Scraper używa `requests` z nagłówkami Chrome (User-Agent, Accept-Language) i parsuje HTML przez BeautifulSoup + lxml.

---

## `scripts/requirements.txt`

```
requests==2.32.3
beautifulsoup4==4.12.3
lxml==5.3.0
python-dateutil==2.9.0
```

---

## `scripts/scrape_tge.py` — architektura

### Stałe

```python
TGE_BASE_URL = "https://tge.pl/energia-elektryczna-rdn"
WARSAW_TZ = ZoneInfo("Europe/Warsaw")
OUTPUT_DIR = "data/prices"
MIN_PRICE, MAX_PRICE = -500.0, 10_000.0  # PLN/MWh
MIN_HOURS, MAX_HOURS = 23, 25            # DST: 23/24/25 godzin
```

### Funkcje

| Funkcja | Opis |
|---------|------|
| `get_html_requests(url)` | Pobiera HTML z nagłówkami Chrome |
| `parse_html_table(html, delivery_date)` | Parsuje `#rdn > tbody`, filtruje `_H\d{2}$`, zwraca `list[float]` |
| `_verify_page_date(soup, delivery_date)` | Sprawdza datę dostawy w `.kontrakt-date` (ostrzeżenie) |
| `_parse_price(text)` | Parsuje ceny w formacie polskim (`312,50`, `1 234,56`, `1.234,56`) |
| `build_price_list(delivery_date, prices)` | Buduje `[{time, price}]` z UTC offset Warsaw (DST-aware) |
| `validate_prices(prices, delivery_date)` | Waliduje liczbę godzin, zakres cen, daty |
| `save_prices(delivery_date, prices, force)` | Zapisuje JSON + aktualizuje `index.json` |
| `verify_prices(delivery_date, fresh_prices)` | Porównuje świeże dane z zapisanym plikiem JSON |
| `fetch_and_parse(delivery_date)` | Orkiestracja: pobierz → parsuj → waliduj |
| `main(argv)` | CLI entry point z argparse |

### CLI

```bash
python scripts/scrape_tge.py                        # data dostawy = jutro
python scripts/scrape_tge.py 2026-03-01              # konkretna data (backfill)
python scripts/scrape_tge.py --force 2026-03-01      # nadpisz istniejący plik
python scripts/scrape_tge.py --verify 2026-03-01     # porównaj z zapisanym JSON
DELIVERY_DATE=2026-03-01 python scripts/scrape_tge.py  # env var (GitHub Actions)
```

| Parametr | Opis |
|----------|------|
| `date` | Pozycyjny, opcjonalny. Data dostawy YYYY-MM-DD (domyślnie: jutro) |
| `--force` | Nadpisuje istniejący plik JSON |
| `--verify` | Pobiera dane i porównuje z zapisanym JSON (nie modyfikuje pliku) |

Zmienna `DELIVERY_DATE` jest fallbackiem — argument pozycyjny ma priorytet.

### Algorytm timestampów (DST)

```
1. Wyznacz lokalną północ dostawy: 00:00 Europe/Warsaw
2. Przelicz na UTC
3. Dla każdego ordinal (0, 1, 2, ...): UTC + ordinal godzin → local Warsaw
```

Dzięki temu:
- Spring-forward (marzec, 23h): ordinal 2 → 03:00+02:00 (przeskok przez 02:00)
- Fall-back (październik, 25h): ordinal 2 → 02:00+02:00, ordinal 3 → 02:00+01:00
- Normalny dzień (24h): ordinal 0..23 → 00:00..23:00

---

## `.github/workflows/scrape-prices.yml`

```yaml
name: Scrape TGE Prices

on:
  schedule:
    - cron: '0 10 * * *'     # 10:00 UTC = 11:00 CET / 12:00 CEST
  workflow_dispatch:
    inputs:
      delivery_date:
        description: Data dostawy YYYY-MM-DD (domyślnie jutro)
        required: false
        type: string

permissions:
  contents: write

jobs:
  scrape:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: '3.12'
          cache: 'pip'
          cache-dependency-path: 'scripts/requirements.txt'
      - run: pip install -r scripts/requirements.txt
      - run: python scripts/scrape_tge.py
        env:
          PYTHONUNBUFFERED: "1"
          DELIVERY_DATE: ${{ inputs.delivery_date }}
      - name: Commit and push
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/prices/
          if git diff --staged --quiet; then
            echo "Brak nowych danych."
          else
            DELIVERY_DATE=$(python -c "
          import json; idx = json.load(open('data/prices/index.json'))
          print(idx.get('latest', 'unknown'))")
            git commit -m "data: ceny TGE Fixing I dla ${DELIVERY_DATE}"
            git push
          fi
      - name: Upload debug screenshot on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: debug-screenshot-${{ github.run_id }}
          path: debug_screenshot.png
          if-no-files-found: ignore
          retention-days: 7
```

TGE publikuje Fixing I o **10:30 czasu polskiego**. Scraper uruchamia się z 30-minutowym marginesem.

---

## Edge cases

### 1. Zmiana czasu (DST)

Format `time` z offsetem strefy czasowej obsługuje DST naturalnie:

- **Spring-forward** (marzec): 23 godziny, brak 02:00, offset zmienia się z `+01:00` na `+02:00`
- **Fall-back** (październik): 25 godzin, dwa wpisy o 02:00 z różnymi offsetami

### 2. Plik już istnieje

Domyślnie pomijany (exit 0). Z `--force` nadpisywany.

### 3. Weryfikacja danych

Flaga `--verify` pozwala pobrać dane ponownie i porównać z zapisanym plikiem:
- Sprawdza liczbę godzin, wartości `time` i `price`
- Raportuje różnice na stderr
- Exit code: 0 (zgodne) lub 1 (różnice/brak pliku)

### 4. Brak danych na stronie TGE

Skrypt zakończy się z kodem 1 i komunikatem z możliwymi przyczynami (za wcześnie, błędny URL, zmiana struktury, blokada).

### 5. Weekendy i święta TGE

TGE działa 365 dni w roku — brak specjalnej obsługi.

---

## Definition of Done

- [x] `scripts/scrape_tge.py` poprawnie scrapuje 24 ceny z TGE (23/25 przy DST)
- [x] `scripts/requirements.txt` zawiera zależności (requests, beautifulsoup4, lxml)
- [x] `.github/workflows/scrape-prices.yml` uruchamia się wg harmonogramu
- [x] Workflow commituje i pushuje nowe pliki JSON do `data/prices/`
- [x] `data/prices/index.json` jest aktualizowany po każdym scrape
- [x] GitHub Pages skonfigurowane i pliki JSON dostępne publicznie
- [x] Workflow działa przy ręcznym uruchomieniu (`workflow_dispatch`)
- [x] `--force` pozwala nadpisać istniejący plik
- [x] `--verify` pozwala porównać dane z zapisanym plikiem
