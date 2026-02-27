#!/usr/bin/env python3
"""
Scraper cen energii TGE — Rynek Dnia Następnego, Fixing I.

Pobiera godzinowe ceny energii elektrycznej z:
  https://wyniki.tge.pl/pl/wyniki/rdn/fixing-I/

i zapisuje jako JSON do data/prices/YYYY-MM-DD.json.

Format wyjściowy:
  {
    "date": "2026-02-28",
    "scraped_at": "2026-02-27T10:05:32Z",
    "unit": "PLN/MWh",
    "prices": [
      {"time": "2026-02-28 00:00:00+01:00", "price": 312.50},
      ...
    ]
  }

Uruchomienie:
  python scripts/scrape_tge.py                        # data dostawy = jutro
  DELIVERY_DATE=2026-03-01 python scripts/scrape_tge.py  # konkretna data

WAŻNE po pierwszym uruchomieniu:
  Otwórz https://wyniki.tge.pl/pl/wyniki/rdn/fixing-I/ w przeglądarce z DevTools
  → Network → Fetch/XHR i sprawdź czy dane ładowane są przez ukryty API endpoint.
  Jeśli tak — zastąp get_html_playwright() prostą funkcją requests/httpx,
  co znacznie przyspieszy działanie scrapera.
"""

import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TGE_URL = "https://wyniki.tge.pl/pl/wyniki/rdn/fixing-I/"
WARSAW_TZ = ZoneInfo("Europe/Warsaw")
OUTPUT_DIR = "data/prices"

# Sanity checks — ceny energii w Polsce (PLN/MWh)
MIN_PRICE = -500.0    # Ujemne ceny możliwe przy nadpodaży OZE
MAX_PRICE = 10_000.0

# Liczba godzin: 23 (spring-forward), 24 (normalny), 25 (fall-back)
MIN_HOURS = 23
MAX_HOURS = 25


# ---------------------------------------------------------------------------
# Pobieranie HTML
# ---------------------------------------------------------------------------

def get_html_playwright(url: str) -> str:
    """
    Pobiera HTML strony przy użyciu Playwright (headless Chromium).

    Wymaga zainstalowanego playwright i Chromium:
      pip install playwright
      playwright install --with-deps chromium
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            locale="pl-PL",
            timezone_id="Europe/Warsaw",
        )
        page = context.new_page()
        page.set_extra_http_headers({
            "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://wyniki.tge.pl/",
        })

        print(f"Ładowanie strony: {url}", file=sys.stderr)
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)

        # Czekaj na tabelę z danymi
        # WAŻNE: Po inspekcji strony zaktualizuj selektor do konkretnej tabeli Fixing I
        try:
            page.wait_for_selector("table", timeout=30_000)
        except Exception:
            screenshot_path = "debug_screenshot.png"
            page.screenshot(path=screenshot_path)
            browser.close()
            raise RuntimeError(
                "Tabela nie załadowała się w ciągu 30 sekund.\n"
                f"Zrzut ekranu zapisany: {screenshot_path}\n"
                "Sprawdź czy TGE nie zmieniło struktury strony."
            )

        # Dodatkowe oczekiwanie na wypełnienie tabeli przez JavaScript
        try:
            page.wait_for_function(
                "() => document.querySelectorAll('table tr').length > 5",
                timeout=15_000,
            )
        except Exception:
            pass  # Kontynuuj — tabela może być gotowa z innymi selektorami

        html = page.content()
        browser.close()

    print("HTML pobrany pomyślnie.", file=sys.stderr)
    return html


# ---------------------------------------------------------------------------
# Parsowanie HTML
# ---------------------------------------------------------------------------

def parse_html_table(html: str, delivery_date: date) -> dict[str, float]:
    """
    Parsuje HTML strony TGE i wyciąga ceny z kolumny Fixing I.

    Zwraca słownik: etykieta_godziny → cena (PLN/MWh)
    Przykład normalny:  {"01": 312.50, "02": 298.00, ..., "24": 300.00}
    Fall-back (październik): {"01": ..., "02": ..., "02A": ..., "03": ..., "25": ...}

    Format instrumentów w tabeli TGE: "YYYY-MM-DD_H01", "YYYY-MM-DD_H02A" itp.

    WAŻNE: Po inspekcji strony w DevTools zweryfikuj:
      1. Selektor tabeli (może być kilka tabel na stronie)
      2. Indeks/nagłówek kolumny Fixing I
      3. Format etykiet instrumentów
    """
    from bs4 import BeautifulSoup

    date_str = delivery_date.strftime("%Y-%m-%d")
    soup = BeautifulSoup(html, "lxml")
    hour_to_price: dict[str, float] = {}

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        # Nagłówki z pierwszego wiersza (lub pierwszej grupy thead)
        header_cells = rows[0].find_all(["th", "td"])
        headers = [c.get_text(strip=True) for c in header_cells]

        if not headers:
            continue

        fixing_col_idx = _find_fixing_column(headers)
        if fixing_col_idx is None:
            print(
                f"DEBUG: Tabela z nagłówkami {headers[:6]}... — brak kolumny Fixing I, pomijam.",
                file=sys.stderr,
            )
            continue

        print(
            f"Znaleziono kolumnę Fixing I: indeks {fixing_col_idx} "
            f"(nagłówek: '{headers[fixing_col_idx]}')",
            file=sys.stderr,
        )

        # Wiersze danych
        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if not cells or fixing_col_idx >= len(cells):
                continue

            instrument = cells[0].get_text(strip=True)

            # Dopasuj format: "YYYY-MM-DD_H01", "YYYY-MM-DD_H02A"
            # Obsługuje też wariant z małą literą: "h01"
            pattern = rf"^{re.escape(date_str)}_[Hh](\d{{2}}[A-Za-z]?)$"
            match = re.match(pattern, instrument)
            if not match:
                continue

            hour_label = match.group(1).upper()  # "01", "24", "02A"

            price_text = cells[fixing_col_idx].get_text(strip=True)
            price = _parse_price(price_text)
            if price is None:
                print(
                    f"WARN: nie można sparsować ceny '{price_text}' dla {instrument}",
                    file=sys.stderr,
                )
                continue

            hour_to_price[hour_label] = price

    return hour_to_price


def _find_fixing_column(headers: list[str]) -> int | None:
    """
    Znajdź indeks kolumny z ceną Fixing I.

    Sprawdza kolejno kilka wariantów nazw nagłówków.
    WAŻNE: Zweryfikuj z rzeczywistą stroną i zaktualizuj listę kandydatów!
    """
    # Kandydaci w kolejności priorytetu — dopasowanie częściowe (case-insensitive)
    candidates = [
        "fixing i kurs",
        "fixing 1 kurs",
        "kurs fixing i",
        "kurs fixing 1",
        "fixing i",
        "fixing 1",
        "kurs jednolity",
        "kurs fix",
    ]

    headers_lower = [h.lower().replace("\xa0", " ").strip() for h in headers]

    for candidate in candidates:
        for i, h in enumerate(headers_lower):
            if candidate in h:
                return i

    return None


def _parse_price(text: str) -> float | None:
    """
    Parsuje cenę z tekstu TGE.

    Obsługuje formaty:
      - "312,50"    (format polski z przecinkiem)
      - "312.50"    (format z kropką)
      - "1 234,56"  (tysiące rozdzielone spacją)
      - "1.234,56"  (tysiące z kropką, dziesiętne z przecinkiem)
      - "-"         (brak ceny — pomijamy)
    """
    text = text.strip().replace("\xa0", "").replace("\u202f", "")

    if text in ("", "-", "—", "N/A", "n/a"):
        return None

    # Usuń spacje jako separator tysięcy
    text = text.replace(" ", "")

    if "," in text and "." in text:
        # Format "1.234,56" → "1234.56"
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        # Format "312,50" → "312.50"
        text = text.replace(",", ".")

    try:
        return float(text)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Budowanie listy z timestampami
# ---------------------------------------------------------------------------

def build_price_list(delivery_date: date, hour_to_price: dict[str, float]) -> list[dict]:
    """
    Konwertuje słownik etykiet TGE na posortowaną listę obiektów:
        [{"time": "YYYY-MM-DD HH:MM:SS+HH:MM", "price": 312.50}, ...]

    Kluczowy algorytm:
      1. Posortuj etykiety TGE chronologicznie (H01 < H02 < H02A < H03 < ...)
      2. Użyj pozycji ordinalnej (0, 1, 2, ...) jako liczby godzin od lokalnej północy
      3. Przelicz przez UTC → automatyczna obsługa DST (spring-forward, fall-back)

    Dlaczego przez UTC zamiast bezpośrednio local + timedelta?
      datetime + timedelta w strefie czasowej przechodzi przez DST niepoprawnie.
      Konwersja przez UTC zawsze daje właściwy offset i poprawny czas zegarowy.

    Przykład fall-back (2026-10-25):
      ordinal 0 → 00:00+02:00 (H01, CEST)
      ordinal 2 → 02:00+02:00 (H02A, CEST — przed cofnięciem zegarka)
      ordinal 3 → 02:00+01:00 (H03, CET — po cofnięciu zegarka)
    """
    sorted_labels = sorted(hour_to_price.keys(), key=_sort_key)

    # Lokalna północ dnia dostawy → UTC
    local_midnight = datetime(
        delivery_date.year, delivery_date.month, delivery_date.day,
        0, 0, 0,
        tzinfo=WARSAW_TZ,
    )
    midnight_utc = local_midnight.astimezone(ZoneInfo("UTC"))

    result = []
    for ordinal, label in enumerate(sorted_labels):
        utc_dt = midnight_utc + timedelta(hours=ordinal)
        local_dt = utc_dt.astimezone(WARSAW_TZ)
        result.append({
            "time": _format_local_dt(local_dt),
            "price": hour_to_price[label],
        })

    return result


def _sort_key(label: str) -> tuple[int, int]:
    """
    Klucz sortowania etykiet TGE: H01 < H02 < H02A < H03 < ... < H24 < H25.
    Cyfry rosnąco, sufiks literowy ("A") po numerze bazowym.
    """
    num = int(re.sub(r"[A-Za-z]", "", label))
    has_suffix = 1 if re.search(r"[A-Za-z]", label) else 0
    return (num, has_suffix)


def _format_local_dt(dt: datetime) -> str:
    """Formatuje datetime jako 'YYYY-MM-DD HH:MM:SS±HH:MM'."""
    offset = dt.utcoffset()
    total_seconds = int(offset.total_seconds())
    sign = "+" if total_seconds >= 0 else "-"
    total_seconds = abs(total_seconds)
    offset_str = f"{sign}{total_seconds // 3600:02d}:{(total_seconds % 3600) // 60:02d}"
    return dt.strftime("%Y-%m-%d %H:%M:%S") + offset_str


# ---------------------------------------------------------------------------
# Walidacja
# ---------------------------------------------------------------------------

def validate_prices(prices: list[dict], delivery_date: date) -> None:
    """
    Sprawdza poprawność pobranych danych.
    Rzuca ValueError przy wykryciu problemu.
    """
    n = len(prices)
    if n < MIN_HOURS or n > MAX_HOURS:
        raise ValueError(
            f"Nieoczekiwana liczba godzin: {n} (oczekiwano {MIN_HOURS}–{MAX_HOURS}). "
            "Możliwa zmiana struktury strony TGE lub problem z DST."
        )

    date_str = delivery_date.strftime("%Y-%m-%d")
    for entry in prices:
        if not entry["time"].startswith(date_str):
            raise ValueError(
                f"Błędna data w danych: '{entry['time']}'. "
                f"Oczekiwano daty {date_str}."
            )
        p = entry["price"]
        if not (MIN_PRICE <= p <= MAX_PRICE):
            raise ValueError(
                f"Cena poza dozwolonym zakresem: {p} PLN/MWh "
                f"(limit: {MIN_PRICE}–{MAX_PRICE})."
            )

    vals = [e["price"] for e in prices]
    print(
        f"Walidacja OK: {n} godzin | "
        f"min={min(vals):.2f} max={max(vals):.2f} avg={sum(vals)/n:.2f} PLN/MWh",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# Zapis do pliku
# ---------------------------------------------------------------------------

def save_prices(delivery_date: date, prices: list[dict]) -> None:
    """
    Zapisuje ceny do data/prices/YYYY-MM-DD.json i aktualizuje index.json.
    Nie nadpisuje istniejącego pliku.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    date_str = delivery_date.strftime("%Y-%m-%d")
    price_file = os.path.join(OUTPUT_DIR, f"{date_str}.json")

    if os.path.exists(price_file):
        print(f"Plik {price_file} już istnieje — pomijam zapis.", file=sys.stderr)
        return

    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = {
        "date": date_str,
        "scraped_at": scraped_at,
        "unit": "PLN/MWh",
        "prices": prices,
    }

    with open(price_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Zapisano: {price_file} ({len(prices)} godzin)", file=sys.stderr)

    _update_index(date_str, scraped_at)


def _update_index(date_str: str, updated_at: str) -> None:
    index_file = os.path.join(OUTPUT_DIR, "index.json")

    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            index = json.load(f)
    else:
        index = {"dates": []}

    if date_str not in index["dates"]:
        index["dates"].append(date_str)
        index["dates"].sort()

    index["latest"] = index["dates"][-1]
    index["updated_at"] = updated_at

    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    print(f"Zaktualizowano: {index_file}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Główna funkcja
# ---------------------------------------------------------------------------

def main() -> None:
    # Obsługa zmiennej środowiskowej DELIVERY_DATE (do backfillingu i workflow_dispatch)
    delivery_date_str = os.environ.get("DELIVERY_DATE", "").strip()
    if delivery_date_str:
        try:
            delivery_date = date.fromisoformat(delivery_date_str)
        except ValueError:
            print(
                f"ERROR: Nieprawidłowy format DELIVERY_DATE='{delivery_date_str}'. "
                "Oczekiwano YYYY-MM-DD.",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        delivery_date = date.today() + timedelta(days=1)

    date_str = delivery_date.strftime("%Y-%m-%d")
    print(f"=== Scraper TGE Fixing I | data dostawy: {date_str} ===", file=sys.stderr)

    # Sprawdź czy plik już istnieje
    price_file = os.path.join(OUTPUT_DIR, f"{date_str}.json")
    if os.path.exists(price_file):
        print(f"Plik {price_file} już istnieje — nic do zrobienia.", file=sys.stderr)
        sys.exit(0)

    # Krok 1: pobierz HTML
    try:
        html = get_html_playwright(TGE_URL)
    except Exception as e:
        print(f"ERROR: Nie udało się pobrać strony TGE: {e}", file=sys.stderr)
        sys.exit(1)

    # Krok 2: parsuj tabelę
    hour_to_price = parse_html_table(html, delivery_date)

    if not hour_to_price:
        print(
            f"\nERROR: Nie znaleziono cen dla daty {date_str}.\n"
            "\nMożliwe przyczyny:\n"
            "  1. TGE jeszcze nie opublikowało cen (za wcześnie — normalna publikacja o 10:30)\n"
            "  2. Strona TGE zmieniła strukturę tabeli\n"
            "  3. Scraper zablokowany przez TGE (bot detection)\n"
            "  4. Błędna data — sprawdź czy delivery_date = jutro\n"
            "\nZalecana akcja: uruchom workflow_dispatch ręcznie lub sprawdź stronę w przeglądarce.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(
        f"Znaleziono {len(hour_to_price)} instrumentów: {sorted(hour_to_price.keys())}",
        file=sys.stderr,
    )

    # Krok 3: buduj listę z timestampami
    prices = build_price_list(delivery_date, hour_to_price)

    # Krok 4: waliduj
    try:
        validate_prices(prices, delivery_date)
    except ValueError as e:
        print(f"ERROR walidacji danych: {e}", file=sys.stderr)
        sys.exit(1)

    # Krok 5: zapisz
    save_prices(delivery_date, prices)
    print("=== Gotowe ===", file=sys.stderr)


if __name__ == "__main__":
    main()
