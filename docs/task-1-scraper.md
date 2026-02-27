# Zadanie 1: Scraper TGE + GitHub Actions + GitHub Pages

## Cel

Codzienne automatyczne pobieranie godzinowych cen energii elektrycznej (Fixing I) z TGE, zapisywanie ich jako pliki JSON w repozytorium i udostępnianie przez GitHub Pages.

## Efekt końcowy

Po realizacji tego zadania:
1. GitHub Actions uruchamia się codziennie o 11:00 CET
2. Skrypt scrapuje `https://wyniki.tge.pl/pl/wyniki/rdn/fixing-I/`
3. Pobrane ceny zapisywane są jako `data/prices/YYYY-MM-DD.json`
4. `data/prices/index.json` jest aktualizowany
5. Zmiany są commitowane i pushowane do gałęzi `main`
6. Pliki JSON są dostępne publicznie przez GitHub Pages

---

## Pliki do stworzenia

```
.github/
  workflows/
    scrape-prices.yml
scripts/
  scrape_tge.py
  requirements.txt
data/
  prices/
    index.json          ← pusty inicjalnie, uzupełniany przez scraper
```

---

## Krok 0: Rozpoznanie struktury strony TGE (WYMAGANE przed implementacją)

Przed napisaniem scrapera **ręcznie zbadaj stronę** w przeglądarce:

1. Otwórz `https://wyniki.tge.pl/pl/wyniki/rdn/fixing-I/`
2. Otwórz DevTools → zakładka **Network** → filtr: **Fetch/XHR**
3. Odśwież stronę
4. Szukaj requestów zwracających JSON z cenami (kolumna "Type: fetch" lub "xhr")
5. Jeśli znajdziesz API endpoint — użyj podejścia **A (requests)**
6. Jeśli dane są renderowane przez JS bez osobnych requestów — użyj podejścia **B (Playwright)**

### Podejście A: Ukryte API (preferowane)

Jeśli strona ładuje dane przez XHR/Fetch do własnego API:
- Zanotuj URL endpointu, metodę HTTP, potrzebne headery/cookies
- Scraper używa `requests` lub `httpx` — szybszy, bez Chromium
- Przykład URL: `https://wyniki.tge.pl/api/rdn/results?date=2026-02-28&type=fixing-1`

### Podejście B: Playwright (fallback)

Jeśli dane renderowane są bezpośrednio w DOM przez JavaScript:
- Użyj `playwright-python` z headless Chromium
- Poczekaj na załadowanie tabeli (selector)
- Sparsuj HTML tabeli

---

## `scripts/requirements.txt`

```
playwright==1.50.0
beautifulsoup4==4.12.3
lxml==5.3.0
python-dateutil==2.9.0
```

> Jeśli używasz Podejścia A (requests), usuń playwright i dodaj `requests==2.32.3` lub `httpx==0.28.1`.

---

## `scripts/scrape_tge.py` — specyfikacja

### Wejście

Skrypt uruchamiany bez argumentów. Data dostawy obliczana automatycznie:
```python
from datetime import date, timedelta
delivery_date = date.today() + timedelta(days=1)  # jutro
```

### Logika scrapowania (Podejście B — Playwright)

```python
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json, re
from datetime import date, timedelta, timezone, datetime
from zoneinfo import ZoneInfo
import sys, os

TGE_URL = "https://wyniki.tge.pl/pl/wyniki/rdn/fixing-I/"
WARSAW_TZ = ZoneInfo("Europe/Warsaw")


def scrape_prices(delivery_date: date) -> list[dict]:
    """
    Scrapuje stronę TGE i zwraca posortowaną listę obiektów:
        [{"time": "2026-02-28 00:00:00+01:00", "price": 312.50}, ...]

    Pole 'time' zawiera ISO 8601 z offsetem strefy czasowej Europe/Warsaw.
    Lista ma 24 elementy dla zwykłego dnia, 23 przy spring-forward, 25 przy fall-back.
    """
    date_str = delivery_date.strftime("%Y-%m-%d")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/121.0.0.0 Safari/537.36",
            locale="pl-PL",
        )
        page = context.new_page()
        page.set_extra_http_headers({
            "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

        page.goto(TGE_URL, wait_until="networkidle", timeout=60_000)

        # Poczekaj na tabelę z danymi
        # WAŻNE: Zaktualizuj selektor po inspekcji strony w DevTools
        page.wait_for_selector("table", timeout=30_000)

        html = page.content()
        browser.close()

    return parse_html_table(html, delivery_date)


def parse_html_table(html: str, delivery_date: date) -> list[dict]:
    """
    Parsuje HTML strony TGE i wyciąga ceny z kolumny Fixing I.

    Struktura tabeli (do weryfikacji po inspekcji):
    - Wiersze: YYYY-MM-DD_H01, YYYY-MM-DD_H02, ..., YYYY-MM-DD_H24
    - Kolumny: Instrument | Kurs | Wolumen | ... | Fixing I Kurs | Fixing I Wolumen | ...

    TGE używa konwencji H01–H24, gdzie:
      H01 = godzina zaczynająca się o 00:00 (midnight)
      H24 = godzina zaczynająca się o 23:00

    Przy zmianie czasu TGE może użyć H02A (fall-back) lub pominąć H02/H03 (spring-forward).
    WAŻNE: Zweryfikuj zachowanie TGE przy zmianie czasu i dostosuj poniższy kod.
    """
    date_str = delivery_date.strftime("%Y-%m-%d")
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")

    hour_to_price: dict[str, float] = {}  # klucz: etykieta TGE np. "H01", "H02A"

    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]

        # Zlokalizuj kolumnę "Fixing I Kurs" (lub podobna)
        # WAŻNE: Dostosuj do rzeczywistych nagłówków po inspekcji strony
        fixing_col_idx = None
        for i, h in enumerate(headers):
            if "Fixing" in h and ("Kurs" in h or "Cena" in h or h == "Fixing I"):
                fixing_col_idx = i
                break

        if fixing_col_idx is None:
            continue

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue

            instrument = cells[0].get_text(strip=True)  # np. "2026-02-28_H01"

            # Wyciągnij etykietę godziny z instrumentu
            pattern = rf"^{re.escape(date_str)}_H(\d{{2}}[A-Z]?)$"
            match = re.match(pattern, instrument)
            if not match:
                continue

            hour_label = match.group(1)  # "01", "02", "02A", "24"

            price_text = cells[fixing_col_idx].get_text(strip=True)
            price_text = price_text.replace(",", ".").replace(" ", "").replace("\xa0", "")

            try:
                price = float(price_text)
            except ValueError:
                print(f"WARN: nie można sparsować ceny '{price_text}' dla {instrument}",
                      file=sys.stderr)
                continue

            hour_to_price[hour_label] = price

    if not hour_to_price:
        raise ValueError(
            f"Nie znaleziono żadnych cen dla daty {date_str}. "
            "Sprawdź strukturę tabeli na stronie TGE."
        )

    return build_price_list(delivery_date, hour_to_price)


def build_price_list(delivery_date: date, hour_to_price: dict[str, float]) -> list[dict]:
    """
    Konwertuje mapę {etykieta_TGE: cena} na posortowaną listę
    [{"time": "YYYY-MM-DD HH:MM:SS+HH:MM", "price": ...}, ...].

    Etykiety TGE H01–H24: H01 = 00:00, H24 = 23:00.
    Specjalna etykieta H02A (przy fall-back) = powtórna godzina 02:00 w czasie zimowym.
    """
    result = []

    for label, price in sorted(hour_to_price.items(), key=_sort_key):
        wall_hour = _label_to_wall_hour(label)  # godzina 0-23

        # Określ fold dla godziny 2:00 przy fall-back
        fold = 1 if label == "H02A" else 0

        local_dt = datetime(
            delivery_date.year, delivery_date.month, delivery_date.day,
            wall_hour, 0, 0,
            tzinfo=WARSAW_TZ,
            fold=fold,
        )

        # Formatuj jako "YYYY-MM-DD HH:MM:SS+HH:MM"
        offset = local_dt.utcoffset()
        total_seconds = int(offset.total_seconds())
        sign = "+" if total_seconds >= 0 else "-"
        total_seconds = abs(total_seconds)
        offset_str = f"{sign}{total_seconds // 3600:02d}:{(total_seconds % 3600) // 60:02d}"
        time_str = local_dt.strftime(f"%Y-%m-%d %H:%M:%S") + offset_str

        result.append({"time": time_str, "price": price})

    return result


def _sort_key(item: tuple[str, float]) -> tuple[int, int]:
    """Sortuje etykiety: H01 < H02 < H02A < H03 < ... < H24."""
    label = item[0]
    num = int(label.rstrip("A"))
    is_a = 1 if label.endswith("A") else 0
    return (num, is_a)


def _label_to_wall_hour(label: str) -> int:
    """H01 → 0, H02 → 1, ..., H24 → 23, H02A → 2 (powtórna)."""
    return int(label.rstrip("A")) - 1


def save_prices(delivery_date: date, prices: list[dict], output_dir: str = "data/prices"):
    """Zapisuje ceny do pliku JSON i aktualizuje index.json."""
    os.makedirs(output_dir, exist_ok=True)

    date_str = delivery_date.strftime("%Y-%m-%d")
    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    data = {
        "date": date_str,
        "scraped_at": scraped_at,
        "unit": "PLN/MWh",
        "prices": prices,
    }

    price_file = os.path.join(output_dir, f"{date_str}.json")
    with open(price_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Zapisano: {price_file} ({len(prices)} godzin)")

    # Aktualizuj index.json
    index_file = os.path.join(output_dir, "index.json")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            index = json.load(f)
    else:
        index = {"dates": []}

    if date_str not in index["dates"]:
        index["dates"].append(date_str)
        index["dates"].sort()

    index["latest"] = index["dates"][-1]
    index["updated_at"] = scraped_at

    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    print(f"Zaktualizowano: {index_file}")


def main():
    delivery_date = date.today() + timedelta(days=1)
    print(f"Scrapuję ceny dla daty dostawy: {delivery_date}")

    try:
        prices = scrape_prices(delivery_date)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    all_prices = [p["price"] for p in prices]
    print(f"Pobrano {len(prices)} cen godzinowych")
    print(f"Min: {min(all_prices):.2f}, Max: {max(all_prices):.2f}, "
          f"Avg: {sum(all_prices)/len(all_prices):.2f} PLN/MWh")

    save_prices(delivery_date, prices)


if __name__ == "__main__":
    main()
```

### Kluczowe weryfikacje w skrypcie

Skrypt powinien zakończyć się błędem (exit code != 0) jeśli:
- Tabela nie załadowała się w ciągu 30 sekund
- Nie znaleziono żadnych wierszy z datą dostawy
- Liczba godzin jest poza zakresem 23–25
- Którakolwiek cena jest <= 0 lub > 10 000 PLN/MWh (sanity check)
- Plik dla tej daty już istnieje (nie nadpisuj istniejących danych)

---

## `.github/workflows/scrape-prices.yml`

```yaml
name: Scrape TGE Prices

on:
  schedule:
    # 10:00 UTC = 11:00 CET (zima) / 12:00 CEST (lato)
    # TGE publikuje Fixing I o 10:30 czasu polskiego
    - cron: '0 10 * * *'
  workflow_dispatch:  # Możliwość ręcznego uruchomienia

jobs:
  scrape:
    runs-on: ubuntu-latest
    permissions:
      contents: write   # Wymagane do git push

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Install Python dependencies
        run: |
          pip install -r scripts/requirements.txt

      - name: Install Playwright browsers
        run: |
          playwright install --with-deps chromium

      - name: Scrape TGE prices
        run: |
          python scripts/scrape_tge.py

      - name: Commit and push new data
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/prices/
          # Commituj tylko jeśli są zmiany
          git diff --staged --quiet || \
            git commit -m "data: ceny TGE dla $(python -c 'from datetime import date, timedelta; print(date.today() + timedelta(days=1))')"
          git push

      - name: Notify on failure
        if: failure()
        run: |
          echo "::error::Scraping nieudany! Sprawdź logi i zweryfikuj strukturę strony TGE."
```

---

## Konfiguracja GitHub Pages

W ustawieniach repozytorium (`Settings → Pages`):
- **Source:** Deploy from a branch
- **Branch:** `main`
- **Folder:** `/ (root)`

Po konfiguracji Pages, dane będą dostępne pod:
- `https://KrzysztofHajdamowicz.github.io/CenyPradu/data/prices/index.json`
- `https://KrzysztofHajdamowicz.github.io/CenyPradu/data/prices/2026-02-28.json`

**Ważne:** Dodaj plik `.nojekyll` w root repozytorium, żeby GitHub Pages serwowało foldery zaczynające się od `_` i nie przetwarzało HTML przez Jekyll. (Dla naszej struktury nie jest krytyczne, ale to dobra praktyka.)

---

## Edge cases do obsłużenia

### 1. Zmiana czasu (DST)

Format `{"time": "...", "price": ...}` z offsetem strefy czasowej obsługuje DST naturalnie — nie ma potrzeby specjalnych pól w JSON.

- **Przejście na czas letni** (ostatnia niedziela marca, spring forward):
  - Zegar skacze z 02:00 na 03:00 → dzień ma 23 godziny
  - TGE pomija H02 (lub H03 — zweryfikuj)
  - W wynikowym JSON brakuje jednego obiektu; offset zmienia się z `+01:00` na `+02:00` między H01 a H03

- **Przejście na czas zimowy** (ostatnia niedziela października, fall back):
  - Zegar cofa się z 03:00 na 02:00 → dzień ma 25 godzin
  - TGE może oznaczać powtórzoną godzinę jako `H02A`
  - `build_price_list()` obsługuje to przez parametr `fold=1` dla `H02A`
  - W wynikowym JSON dwa obiekty mają `"time": "...02:00:00..."` z różnymi offsetami (`+02:00` i `+01:00`)

**Kluczowe:** Po inspekcji strony TGE przy zmianie czasu zweryfikuj dokładne etykiety instrumentów i dostosuj funkcję `build_price_list()` jeśli konwencja jest inna.

### 2. Strona jeszcze nie opublikowała danych

Jeśli workflow uruchamia się za wcześnie (np. opóźnienie po stronie TGE):
- Sprawdź, czy tabela zawiera wiersze z jutrzejszą datą
- Jeśli nie — zakończ z błędem i informacją w logu
- Alternatywnie: retry z backoffem (max 3 próby co 5 minut)

### 3. Plik już istnieje

Nie nadpisuj istniejącego pliku. Może być uruchomiony ręcznie drugi raz.
```python
if os.path.exists(price_file):
    print(f"Plik {price_file} już istnieje. Pomijam.")
    sys.exit(0)
```

### 4. Weekendy i dni wolne TGE

TGE działa również w weekendy i święta (rynek energii działa 365 dni). Nie ma potrzeby specjalnej obsługi.

---

## Weryfikacja działania

Po wdrożeniu sprawdź:

1. Uruchom workflow ręcznie przez GitHub Actions (`workflow_dispatch`)
2. Sprawdź logi — powinny pokazać liczbę pobranych cen
3. Sprawdź, czy plik `data/prices/YYYY-MM-DD.json` pojawił się w repozytorium
4. Sprawdź `data/prices/index.json`
5. Otwórz `https://KrzysztofHajdamowicz.github.io/CenyPradu/data/prices/index.json` — powinien być dostępny

---

## Definition of Done

- [ ] `scripts/scrape_tge.py` poprawnie scrapuje 24 ceny z TGE
- [ ] `scripts/requirements.txt` zawiera wszystkie zależności
- [ ] `.github/workflows/scrape-prices.yml` uruchamia się wg harmonogramu
- [ ] Workflow commituje i pushuje nowe pliki JSON do `data/prices/`
- [ ] `data/prices/index.json` jest aktualizowany po każdym scrape
- [ ] GitHub Pages skonfigurowane i pliki JSON dostępne publicznie
- [ ] Workflow zakończony sukcesem przy ręcznym uruchomieniu (`workflow_dispatch`)
- [ ] Plik `.nojekyll` istnieje w root repozytorium
