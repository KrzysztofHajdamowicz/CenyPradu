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
  python scripts/scrape_tge.py 2026-03-01                  # konkretna data (backfill)
  python scripts/scrape_tge.py --force                     # nadpisz istniejący plik
  python scripts/scrape_tge.py --verify 2026-03-01         # porównaj z istniejącym JSON
  DELIVERY_DATE=2026-03-01 python scripts/scrape_tge.py   # backfill (kompatybilność)
"""

import argparse
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
# Pobieranie HTML (requests + BeautifulSoup4)
# ---------------------------------------------------------------------------

def get_html_requests(url: str) -> str:
    """
    Pobiera HTML strony przy użyciu requests z nagłówkami przeglądarki.

    Wysyła żądanie GET z User-Agent i nagłówkami Accept typowymi dla Chrome,
    co pozwala ominąć podstawowe blokady po stronie TGE.
    """
    import requests

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    print(f"Ładowanie: {url}", file=sys.stderr)
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    print("HTML pobrany.", file=sys.stderr)
    return response.text


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

def save_prices(delivery_date: date, prices: list[dict], *, force: bool = False) -> None:
    """
    Zapisuje ceny do data/prices/YYYY-MM-DD.json i aktualizuje index.json.
    Nie nadpisuje istniejącego pliku chyba że force=True.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    date_str = delivery_date.strftime("%Y-%m-%d")
    price_file = os.path.join(OUTPUT_DIR, f"{date_str}.json")

    if os.path.exists(price_file) and not force:
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
# Weryfikacja — porównanie świeżo pobranych danych z istniejącym JSON
# ---------------------------------------------------------------------------

def verify_prices(delivery_date: date, fresh_prices: list[dict]) -> bool:
    """
    Porównuje świeżo pobrane ceny z zapisanym plikiem JSON.
    Zwraca True jeśli dane się zgadzają, False jeśli są różnice.
    """
    date_str = delivery_date.strftime("%Y-%m-%d")
    price_file = os.path.join(OUTPUT_DIR, f"{date_str}.json")

    if not os.path.exists(price_file):
        print(f"ERROR: Brak pliku {price_file} do weryfikacji.", file=sys.stderr)
        return False

    with open(price_file, "r", encoding="utf-8") as f:
        saved = json.load(f)

    saved_prices = saved.get("prices", [])
    ok = True

    if len(fresh_prices) != len(saved_prices):
        print(
            f"RÓŻNICA: liczba godzin: pobrane={len(fresh_prices)}, "
            f"zapisane={len(saved_prices)}",
            file=sys.stderr,
        )
        ok = False

    n = min(len(fresh_prices), len(saved_prices))
    diffs = 0
    for i in range(n):
        fp, sp = fresh_prices[i], saved_prices[i]
        time_match = fp["time"] == sp["time"]
        price_match = fp["price"] == sp["price"]

        if not time_match or not price_match:
            diffs += 1
            parts = []
            if not time_match:
                parts.append(f"time: {sp['time']} → {fp['time']}")
            if not price_match:
                parts.append(f"price: {sp['price']} → {fp['price']}")
            print(f"  [{i}] {', '.join(parts)}", file=sys.stderr)

    if diffs:
        print(f"RÓŻNICA: {diffs} godzin(y) z różnymi wartościami.", file=sys.stderr)
        ok = False

    if ok:
        print(
            f"VERIFY OK: {price_file} — {len(fresh_prices)} godzin, "
            "dane zgodne ze źródłem.",
            file=sys.stderr,
        )
    else:
        print(f"VERIFY FAIL: {price_file} — wykryto różnice!", file=sys.stderr)

    return ok


# ---------------------------------------------------------------------------
# Pobieranie i parsowanie — wspólny krok
# ---------------------------------------------------------------------------

def fetch_and_parse(delivery_date: date) -> list[dict]:
    """
    Pobiera HTML z TGE, parsuje tabelę, buduje timestampy i waliduje.
    Zwraca gotową listę price entries lub wywołuje sys.exit(1) przy błędzie.
    """
    date_str = delivery_date.strftime("%Y-%m-%d")

    query_date = delivery_date - timedelta(days=1)
    url = f"{TGE_BASE_URL}?dateShow={query_date.strftime('%d-%m-%Y')}"

    try:
        html = get_html_requests(url)
    except Exception as e:
        print(f"ERROR: Nie udało się pobrać strony: {e}", file=sys.stderr)
        sys.exit(1)

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

    prices = build_price_list(delivery_date, raw_prices)

    try:
        validate_prices(prices, delivery_date)
    except ValueError as e:
        print(f"ERROR walidacji: {e}", file=sys.stderr)
        sys.exit(1)

    return prices


# ---------------------------------------------------------------------------
# CLI i główna funkcja
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scraper cen energii TGE — Rynek Dnia Następnego, Fixing I.",
    )
    parser.add_argument(
        "date",
        nargs="?",
        default=None,
        help="Data dostawy YYYY-MM-DD (domyślnie: jutro).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Nadpisz istniejący plik JSON zamiast go pomijać.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help=(
            "Pobierz dane ze strony TGE i porównaj z istniejącym plikiem JSON. "
            "Nie modyfikuje pliku — służy do weryfikacji poprawności scrapera."
        ),
    )
    return parser.parse_args(argv)


def resolve_delivery_date(args: argparse.Namespace) -> date:
    """Wyznacza datę dostawy z argumentu CLI, zmiennej środowiskowej lub domyślnie jutro."""
    if args.date:
        src = args.date
    else:
        src = os.environ.get("DELIVERY_DATE", "").strip()

    if src:
        try:
            return date.fromisoformat(src)
        except ValueError:
            print(
                f"ERROR: Nieprawidłowa data '{src}'. Oczekiwano YYYY-MM-DD.",
                file=sys.stderr,
            )
            sys.exit(1)

    return date.today() + timedelta(days=1)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    delivery_date = resolve_delivery_date(args)
    date_str = delivery_date.strftime("%Y-%m-%d")

    print(f"=== TGE Fixing I | data dostawy: {date_str} ===", file=sys.stderr)

    if args.verify:
        prices = fetch_and_parse(delivery_date)
        ok = verify_prices(delivery_date, prices)
        sys.exit(0 if ok else 1)

    price_file = os.path.join(OUTPUT_DIR, f"{date_str}.json")
    if os.path.exists(price_file) and not args.force:
        print(f"Plik {price_file} już istnieje — nic do zrobienia.", file=sys.stderr)
        sys.exit(0)

    prices = fetch_and_parse(delivery_date)
    save_prices(delivery_date, prices, force=args.force)
    print("=== Gotowe ===", file=sys.stderr)


if __name__ == "__main__":
    main()
