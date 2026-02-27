# Architektura systemu CenyPradu

## Przegląd

System automatycznie pobiera godzinowe ceny energii elektrycznej z TGE (Towarowa Giełda Energii), zapisuje je jako statyczne pliki JSON w repozytorium i udostępnia wraz z frontendem przez GitHub Pages.

```
┌─────────────────────────────────────────────────────────────────┐
│                         GitHub Actions                          │
│                                                                 │
│  cron: 0 10 * * *   →   scrape_tge.py   →   git commit+push   │
│  (11:00 CET, 12:00 CEST)                                       │
└──────────────────────────────┬──────────────────────────────────┘
                               │ commit
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Repozytorium GitHub                       │
│                                                                 │
│  data/prices/                                                   │
│    index.json              ← lista dostępnych dat               │
│    2026-02-28.json         ← ceny dla daty dostawy              │
│    2026-03-01.json                                              │
│    ...                                                          │
│                                                                 │
│  tariffs/                                                       │
│    tauron-g11.json                                              │
│    tauron-g12.json                                              │
│    energa-g11.json                                              │
│    ...                                                          │
│                                                                 │
│  web/                                                           │
│    index.html                                                   │
│    js/app.js, api.js, tariffs.js                                │
│    css/style.css                                                │
└──────────────────────────────┬──────────────────────────────────┘
                               │ GitHub Pages (auto-deploy z main)
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                         GitHub Pages                            │
│                                                                 │
│  https://<user>.github.io/CenyPradu/                           │
│  ├── data/prices/index.json           ← "API" z listą dat       │
│  ├── data/prices/2026-02-28.json      ← ceny dla dnia           │
│  ├── tariffs/tauron-g11.json          ← taryfa dystrybucji      │
│  └── web/index.html                   ← frontend                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Struktura katalogów

```
CenyPradu/
├── .github/
│   └── workflows/
│       └── scrape-prices.yml       # Faza 1: harmonogram scrapera
│
├── scripts/
│   ├── scrape_tge.py               # Faza 1: scraper Python/Playwright
│   └── requirements.txt            # Faza 1: zależności Pythona
│
├── data/
│   └── prices/
│       ├── index.json              # Faza 1: indeks dostępnych dat
│       └── YYYY-MM-DD.json         # Faza 1: ceny dla daty dostawy
│
├── tariffs/
│   ├── schema.json                 # Faza 2: JSON Schema walidacji
│   ├── tauron-g11.json             # Faza 2: taryfa Tauron G11
│   ├── tauron-g12.json             # Faza 2: taryfa Tauron G12
│   ├── energa-g11.json             # Faza 2: taryfa Energa G11
│   ├── energa-g12.json             # Faza 2: taryfa Energa G12
│   ├── enea-g11.json               # Faza 2: taryfa Enea G11
│   ├── enea-g12.json               # Faza 2: taryfa Enea G12
│   ├── pge-g11.json                # Faza 2: taryfa PGE G11
│   ├── pge-g12.json                # Faza 2: taryfa PGE G12
│   └── stoen-g11.json              # Faza 2: taryfa Stoen G11
│
├── web/
│   ├── index.html                  # Faza 3: główna strona
│   ├── js/
│   │   ├── app.js                  # Faza 3: logika aplikacji
│   │   ├── api.js                  # Faza 3: pobieranie danych JSON
│   │   └── tariffs.js              # Faza 3: kalkulator taryf
│   └── css/
│       └── style.css               # Faza 3: style
│
├── docs/
│   ├── architecture.md             # Ten plik
│   ├── task-1-scraper.md           # Specyfikacja: Faza 1
│   ├── task-2-tariffs.md           # Specyfikacja: Faza 2
│   └── task-3-frontend.md          # Specyfikacja: Faza 3
│
└── README.md
```

---

## Format danych

### `data/prices/YYYY-MM-DD.json`

Data w nazwie pliku to **data dostawy** (dzień, na który ceny obowiązują), nie data scrapowania.

```json
{
  "date": "2026-02-28",
  "scraped_at": "2026-02-27T10:05:32Z",
  "unit": "PLN/MWh",
  "prices": [
    {"time": "2026-02-28 00:00:00+01:00", "price": 312.50},
    {"time": "2026-02-28 01:00:00+01:00", "price": 298.00},
    {"time": "2026-02-28 02:00:00+01:00", "price": 285.00},
    {"time": "2026-02-28 03:00:00+01:00", "price": 270.00},
    "...",
    {"time": "2026-02-28 23:00:00+01:00", "price": 300.00}
  ]
}
```

**Konwencja:**
- `prices` to posortowana lista obiektów `{"time": ..., "price": ...}`
- `time` to ISO 8601 z offsetem strefy czasowej (CET = `+01:00`, CEST = `+02:00`)
- `time` oznacza **początek** godziny dostawy
- Lista ma zazwyczaj 24 elementy (godziny 00:00–23:00)

**Obsługa zmiany czasu — naturalnie przez strefę czasową:**

Przejście na czas letni (marzec, spring forward — 23 godziny):
```json
{
  "prices": [
    {"time": "2026-03-29 00:00:00+01:00", "price": 310.00},
    {"time": "2026-03-29 01:00:00+01:00", "price": 295.00},
    {"time": "2026-03-29 03:00:00+02:00", "price": 320.00},
    "...",
    {"time": "2026-03-29 23:00:00+02:00", "price": 300.00}
  ]
}
```

Przejście na czas zimowy (październik, fall back — 25 godzin):
```json
{
  "prices": [
    {"time": "2026-10-25 00:00:00+02:00", "price": 310.00},
    {"time": "2026-10-25 01:00:00+02:00", "price": 295.00},
    {"time": "2026-10-25 02:00:00+02:00", "price": 320.00},
    {"time": "2026-10-25 02:00:00+01:00", "price": 315.00},
    {"time": "2026-10-25 03:00:00+01:00", "price": 308.00},
    "...",
    {"time": "2026-10-25 23:00:00+01:00", "price": 300.00}
  ]
}
```

Offset strefy czasowej w `time` eliminuje wszelką niejednoznaczność — brak potrzeby specjalnych pól `dst_change`.

### `data/prices/index.json`

```json
{
  "updated_at": "2026-02-27T10:05:35Z",
  "latest": "2026-02-28",
  "dates": [
    "2026-02-01",
    "2026-02-02",
    "...",
    "2026-02-28"
  ]
}
```

### `tariffs/OPERATOR-TARIFA.json`

Szczegółowy format opisany w [task-2-tariffs.md](task-2-tariffs.md).

---

## Harmonogram GitHub Actions

| Czas UTC    | Czas CET (zima) | Czas CEST (lato) | Uwagi                              |
|-------------|-----------------|------------------|------------------------------------|
| `0 10 * * *` | 11:00           | 12:00            | TGE publ. o 10:30 PL               |

Cron: `0 10 * * *` (10:00 UTC = 11:00 CET / 12:00 CEST)

TGE publikuje wyniki Fixing I codziennie o **10:30 czasu polskiego**. Scraper uruchamiany jest o **11:00 CET / 12:00 CEST**, z 30 minutowym marginesem. Dodatkowo workflow_dispatch pozwala na ręczne uruchomienie w razie potrzeby.

---

## GitHub Pages

Repozytorium skonfigurowane z GitHub Pages serwującym z **gałęzi `main`, katalogu `/` (root)**.

Każdy commit scrapera automatycznie "deployuje" nowe dane — brak dodatkowego kroku CI/CD dla danych.

Frontend (Faza 3) — czyste HTML/CSS/JS (brak kroku budowania), serwowany bezpośrednio przez Pages.

---

## Fazy realizacji

### Faza 1: Scraper + dane

**Cel:** Codzienne automatyczne pobieranie cen i ich dostępność przez Pages.

Szczegóły: [task-1-scraper.md](task-1-scraper.md)

### Faza 2: Taryfy dystrybucyjne

**Cel:** Katalog taryf dystrybucji głównych operatorów w Polsce + kalkulator całkowitego kosztu energii.

Szczegóły: [task-2-tariffs.md](task-2-tariffs.md)

### Faza 3: Frontend

**Cel:** Interfejs do przeglądania cen historycznych i bieżących, kalkulatora kosztów z uwzględnieniem taryfy.

Szczegóły: [task-3-frontend.md](task-3-frontend.md)

---

## Kluczowe decyzje architektoniczne

| Decyzja | Wybór | Uzasadnienie |
|---------|-------|--------------|
| Backend | Brak (static) | GitHub Pages + JSON = darmowe, zero maintenance |
| Scraper | Python + Playwright | TGE wymaga JS renderowania; Playwright w GitHub Actions jest standardowe |
| Harmonogram | GitHub Actions cron | Natywna integracja z repo; darmowe dla publicznych repo |
| Storage | Pliki JSON w repo | Brak zewnętrznej bazy; historia = git history; Pages = CDN |
| Frontend | Vanilla JS + Chart.js | Brak buildu, działa bezpośrednio z Pages |
| Taryfy | Statyczne JSONy | Taryfy zmieniają się rzadko; wersjonowanie w git jest wystarczające |

---

## Zależności zewnętrzne i ryzyka

| Ryzyko | Prawdopodobieństwo | Mitygacja |
|--------|-------------------|-----------|
| TGE zmieni strukturę strony | Średnie | Scraper ma testy weryfikujące format danych; alert przy nieoczekiwanym output |
| TGE wdroży anti-bot | Średnie | Playwright z właściwymi headerami; fallback: ręczne uruchomienie workflow_dispatch |
| GitHub Actions przestanie działać | Niskie | workflow_dispatch jako backup; skrypt można uruchomić lokalnie |
| Brakujące dane (np. dzień wolny TGE) | Niskie | Weryfikacja dat w skrypcie; nie nadpisuj istniejących plików |
