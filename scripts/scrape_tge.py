#!/usr/bin/env python3
"""
Scraper cen energii TGE — Rynek Dnia Następnego, Fixing I.

URL strony: https://tge.pl/energia-elektryczna-rdn?dateShow=DD-MM-YYYY
            (dateShow = delivery_date - 1 dzień, format DD-MM-YYYY)

Struktura HTML:
  Tabela: #rdn  (klasy: table table-hover table-rdb)
  Wiersze godzinowe: td[0]="YYYY-MM-DD_H01", td[1]="60", td[2]=cena Fixing I PLN/MWh
  Wiersze 15-min:    td[0]="YYYY-MM-DD_Q00:15", td[1]="15" — ignorujemy
  Data:    .kontrakt-date > small  ("dla dostawy w dniu DD-MM-YYYY")

Format wyjściowy (data/prices/YYYY-MM-DD.json):
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
  python scripts/scrape_tge.py                             # data dostawy = jutro
  DELIVERY_DATE=2026-03-01 python scripts/scrape_tge.py   # konkretna data (backfill)
"""

import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TGE_BASE_URL = "https://tge.pl/energia-elektryczna-rdn"
WARSAW_TZ = ZoneInfo("Europe/Warsaw")
OUTPUT_DIR = "data/prices"

# Sanity checks — historyczny zakres cen energii w Polsce (PLN/MWh)
MIN_PRICE = -500.0    # Ujemne ceny możliwe przy nadpodaży OZE
MAX_PRICE = 10_000.0

# Liczba godzin: 23 (spring-forward), 24 (normalny dzień), 25 (fall-back)
MIN_HOURS = 23
MAX_HOURS = 25


# ---------------------------------------------------------------------------
# Pobieranie HTML (Playwright + headless Chromium)
# ---------------------------------------------------------------------------

def get_html_playwright(url: str) -> str:
    """
    Pobiera wyrenderowany HTML strony przy użyciu Playwright (headless Chromium).

    Strona https://tge.pl zwraca 403 dla zwykłych requestów HTTP — wymagana
    pełna przeglądarka. Czeka na załadowanie tabeli #rdn.
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

        print(f"Ładowanie: {url}", file=sys.stderr)
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)

        # Czekaj na tabelę z cenami
        try:
            page.wait_for_selector("#rdn", timeout=30_000)
        except Exception:
            screenshot_path = "debug_screenshot.png"
            page.screenshot(path=screenshot_path)
            browser.close()
            raise RuntimeError(
                "Tabela #rdn nie załadowała się.\n"
                f"Zrzut ekranu: {screenshot_path}\n"
                "Możliwe: strona TGE zmieniła strukturę lub jeszcze nie ma cen."
            )

        html = page.content()
        browser.close()

    print("HTML pobrany.", file=sys.stderr)
    return html


# ---------------------------------------------------------------------------
# Parsowanie HTML
# ---------------------------------------------------------------------------

def parse_html_table(html: str, delivery_date: date) -> list[float]:
    """
    Parsuje HTML strony TGE i zwraca listę cen Fixing I (PLN/MWh)
    w kolejności chronologicznej (H01, H02, ..., H24; 25 przy fall-back).

    Struktura tabeli (#rdn):
      - td[0]: identyfikator instrumentu, np. "2026-02-28_H01", "2026-02-28_Q00:15"
      - td[1]: typ instrumentu: "60" = godzinowy, "15" = 15-minutowy
      - td[2]: cena Fixing I (PLN/MWh), format: "312,50" lub "1 234,56" lub "-"
      - td[3]: wolumen Fixing I (MWh) — ignorujemy
      - ...

    Filtrujemy tylko wiersze godzinowe: identyfikator kończy się na _H\\d{2}.
    Kolejność wierszy w HTML jest chronologiczna (H01 ... H24/H25).
    Na dzień fall-back H03 pojawi się dwukrotnie (25 wierszy łącznie).
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")

    # Weryfikacja daty z nagłówka strony (ostrzeżenie, nie blokuje)
    _verify_page_date(soup, delivery_date)

    # Wyciągnij ciało tabeli
    tbody = soup.select_one("#rdn > tbody")
    if tbody is None:
        print(
            "ERROR: Nie znaleziono #rdn > tbody.\n"
            "Sprawdź czy strona TGE nie zmieniła struktury.",
            file=sys.stderr,
        )
        return []

    prices: list[float] = []
    for row in tbody.select("tr"):
        tds = row.select("td")
        if len(tds) < 3:
            continue

        instrument = tds[0].get_text(strip=True)

        # Filtruj tylko wiersze godzinowe: np. "2026-02-28_H01", "2026-02-28_H24"
        if not re.search(r"_H\d{2}$", instrument):
            continue

        price_text = tds[2].get_text(strip=True)  # td[3] (1-indexed) = Fixing I kurs
        price = _parse_price(price_text)
        if price is None:
            print(
                f"WARN: nie można sparsować ceny '{price_text}' ({instrument})",
                file=sys.stderr,
            )
            continue

        prices.append(price)
        hour_label = instrument.split("_")[-1]  # "H01", "H02", ...
        print(f"  {hour_label} → {price:.2f} PLN/MWh", file=sys.stderr)

    return prices


def _verify_page_date(soup, delivery_date: date) -> None:
    """
    Weryfikuje datę dostawy z elementu .kontrakt-date na stronie TGE.
    Loguje ostrzeżenie jeśli nie pasuje — nie rzuca wyjątku.

    Element .kontrakt-date ma strukturę:
      <h4 class="kontrakt-date">
        <a>Kontrakty</a>
        <small>dla dostawy w dniu DD-MM-YYYY</small>
      </h4>
    """
    expected = delivery_date.strftime("%d-%m-%Y")

    for el in soup.select(".kontrakt-date"):
        text = el.get_text(strip=True)
        found_dates = re.findall(r"\d{2}-\d{2}-\d{4}", text)
        if not found_dates:
            continue

        page_date = found_dates[-1]  # Data dostawy jest zazwyczaj ostatnią w tekście
        if page_date == expected:
            print(f"Data dostawy potwierdzona: {page_date}", file=sys.stderr)
        else:
            print(
                f"WARN: data na stronie ({page_date}) ≠ oczekiwana ({expected}).\n"
                "  Możliwe: TGE jeszcze nie opublikowało cen lub URL dateShow jest błędny.",
                file=sys.stderr,
            )
        return

    print(
        "WARN: nie znaleziono .kontrakt-date — pomijam weryfikację daty.",
        file=sys.stderr,
    )


def _parse_price(text: str) -> float | None:
    """
    Parsuje cenę z komórki tabeli TGE.

    Obsługiwane formaty:
      "312,50"    → 312.50  (format polski)
      "1 234,56"  → 1234.56 (tysiące rozdzielone spacją)
      "1.234,56"  → 1234.56 (tysiące z kropką, dziesiętne z przecinkiem)
      "-"         → None    (brak ceny)
    """
    text = text.strip().replace("\xa0", " ").replace("\u202f", " ")

    if text in ("", "-", "—", "N/A", "n/a", "brak"):
        return None

    # Usuń separatory tysięcy (spacja, twarda spacja)
    text = text.replace(" ", "")

    if "," in text and "." in text:
        # "1.234,56" → "1234.56"
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        # "312,50" → "312.50"
        text = text.replace(",", ".")

    try:
        return float(text)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Budowanie listy z timestampami ISO 8601
# ---------------------------------------------------------------------------

def build_price_list(delivery_date: date, prices: list[float]) -> list[dict]:
    """
    Konwertuje listę cen (w kolejności chronologicznej) na listę obiektów:
        [{"time": "YYYY-MM-DD HH:MM:SS±HH:MM", "price": 312.50}, ...]

    Algorytm timestamp (poprawna obsługa DST):
      1. Wyznacz lokalną północ dnia dostawy (00:00 czas Warsaw)
      2. Przelicz na UTC
      3. Dla każdego ordinal (0, 1, 2, ...): UTC + ordinal godzin → local Warsaw

    Przykład fall-back (2026-10-25, 25 godzin):
      ordinal 0 → 00:00+02:00 (H01, CEST)
      ordinal 2 → 02:00+02:00 (H03a, CEST — przed cofnięciem zegarka)
      ordinal 3 → 02:00+01:00 (H03b, CET — po cofnięciu zegarka)
      ordinal 24 → 23:00+01:00 (H25, CET)

    Przykład spring-forward (2026-03-29, 23 godziny):
      ordinal 1 → 01:00+01:00 (CET)
      ordinal 2 → 03:00+02:00 (CEST — przeskok przez 02:00)
    """
    local_midnight = datetime(
        delivery_date.year, delivery_date.month, delivery_date.day,
        0, 0, 0,
        tzinfo=WARSAW_TZ,
    )
    midnight_utc = local_midnight.astimezone(ZoneInfo("UTC"))

    result = []
    for ordinal, price in enumerate(prices):
        utc_dt = midnight_utc + timedelta(hours=ordinal)
        local_dt = utc_dt.astimezone(WARSAW_TZ)
        result.append({
            "time": _format_local_dt(local_dt),
            "price": price,
        })

    return result


def _format_local_dt(dt: datetime) -> str:
    """Formatuje datetime jako 'YYYY-MM-DD HH:MM:SS±HH:MM'."""
    offset = dt.utcoffset()
    total_sec = int(offset.total_seconds())
    sign = "+" if total_sec >= 0 else "-"
    total_sec = abs(total_sec)
    return dt.strftime("%Y-%m-%d %H:%M:%S") + f"{sign}{total_sec // 3600:02d}:{(total_sec % 3600) // 60:02d}"


# ---------------------------------------------------------------------------
# Walidacja
# ---------------------------------------------------------------------------

def validate_prices(prices: list[dict], delivery_date: date) -> None:
    """
    Sprawdza poprawność pobranych danych. Rzuca ValueError przy problemie.
    """
    n = len(prices)
    if n < MIN_HOURS or n > MAX_HOURS:
        raise ValueError(
            f"Nieoczekiwana liczba godzin: {n} (oczekiwano {MIN_HOURS}–{MAX_HOURS}).\n"
            "  Sprawdź: zmiana czasu DST, lub błąd parsowania tabeli TGE."
        )

    date_str = delivery_date.strftime("%Y-%m-%d")
    for entry in prices:
        if not entry["time"].startswith(date_str):
            raise ValueError(
                f"Błędna data w danych: '{entry['time']}' (oczekiwano {date_str})."
            )
        p = entry["price"]
        if not (MIN_PRICE <= p <= MAX_PRICE):
            raise ValueError(
                f"Cena poza zakresem: {p} PLN/MWh (limit: {MIN_PRICE}–{MAX_PRICE})."
            )

    vals = [e["price"] for e in prices]
    print(
        f"Walidacja OK: {n} godzin | "
        f"min={min(vals):.2f}  max={max(vals):.2f}  avg={sum(vals)/n:.2f} PLN/MWh",
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
        print(f"Plik {price_file} już istnieje — pomijam.", file=sys.stderr)
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
    print(f"Zapisano: {price_file}  ({len(prices)} godzin)", file=sys.stderr)

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
    # Obsługa DELIVERY_DATE (backfill / workflow_dispatch)
    delivery_date_str = os.environ.get("DELIVERY_DATE", "").strip()
    if delivery_date_str:
        try:
            delivery_date = date.fromisoformat(delivery_date_str)
        except ValueError:
            print(
                f"ERROR: Nieprawidłowy DELIVERY_DATE='{delivery_date_str}'. "
                "Oczekiwano YYYY-MM-DD.",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        delivery_date = date.today() + timedelta(days=1)

    date_str = delivery_date.strftime("%Y-%m-%d")
    print(f"=== TGE Fixing I | data dostawy: {date_str} ===", file=sys.stderr)

    # Wyjdź bez błędu jeśli plik już istnieje
    price_file = os.path.join(OUTPUT_DIR, f"{date_str}.json")
    if os.path.exists(price_file):
        print(f"Plik {price_file} już istnieje — nic do zrobienia.", file=sys.stderr)
        sys.exit(0)

    # URL z parametrem dateShow = delivery_date - 1 dzień
    # (TGE wyświetla ceny następnego dnia, dateShow to data z której przeglądamy)
    query_date = delivery_date - timedelta(days=1)
    url = f"{TGE_BASE_URL}?dateShow={query_date.strftime('%d-%m-%Y')}"

    # Krok 1: pobierz HTML
    try:
        html = get_html_playwright(url)
    except Exception as e:
        print(f"ERROR: Nie udało się pobrać strony: {e}", file=sys.stderr)
        sys.exit(1)

    # Krok 2: parsuj tabelę
    raw_prices = parse_html_table(html, delivery_date)
    if not raw_prices:
        print(
            f"\nERROR: Brak cen dla daty {date_str}.\n"
            "\nMożliwe przyczyny:\n"
            "  1. TGE nie opublikowało jeszcze cen (normalna publikacja o 10:30)\n"
            "  2. Błędny parametr dateShow — sprawdź logikę delivery_date - 1 dzień\n"
            "  3. Strona TGE zmieniła strukturę tabeli\n"
            "  4. Strona zablokowała scraper (sprawdź debug_screenshot.png)\n"
            f"\nURL próbowany: {url}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Znaleziono {len(raw_prices)} godzin.", file=sys.stderr)

    # Krok 3: buduj timestampy
    prices = build_price_list(delivery_date, raw_prices)

    # Krok 4: waliduj
    try:
        validate_prices(prices, delivery_date)
    except ValueError as e:
        print(f"ERROR walidacji: {e}", file=sys.stderr)
        sys.exit(1)

    # Krok 5: zapisz
    save_prices(delivery_date, prices)
    print("=== Gotowe ===", file=sys.stderr)


if __name__ == "__main__":
    main()
