# Zadanie 3: Frontend

## Cel

Czysta, prosta aplikacja webowa (SPA bez frameworka, bez buildu) serwowana przez GitHub Pages, umożliwiająca przeglądanie cen energii TGE w formie wykresu oraz kalkulację całkowitego kosztu z uwzględnieniem taryfy dystrybucji.

---

## Stack technologiczny

| Warstwa | Technologia | Uzasadnienie |
|---------|-------------|--------------|
| HTML | Vanilla HTML5 | Brak buildu, GitHub Pages bez konfiguracji |
| CSS | Tailwind CSS (CDN) | Szybki development, responsywność out-of-box |
| JS | Vanilla ES2022 (modules) | Brak bundlera, natywne `import/export` |
| Wykresy | Chart.js 4.x (CDN) | Dojrzała biblioteka, łatwe wykresy słupkowe i liniowe |
| Daty | Day.js (CDN) | Lekki, wystarczający do operacji na datach |

Brak npm, brak webpack, brak React. Pliki serwowane bezpośrednio.

---

## Struktura plików

```
web/
├── index.html              ← Główna strona
├── js/
│   ├── app.js              ← Punkt wejścia, inicjalizacja
│   ├── api.js              ← Pobieranie danych z JSON (fetch)
│   ├── chart.js            ← Konfiguracja i renderowanie Chart.js
│   ├── tariffs.js          ← Logika kalkulatora taryf (z task-2)
│   └── holidays.js         ← Polskie święta dla logiki taryf G12
└── css/
    └── style.css           ← Tylko niestandardowe style (animacje itp.)
```

---

## Makieta interfejsu

```
┌────────────────────────────────────────────────────────────────────┐
│  CenyPradu ⚡                                   [dziś] [historia] │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  Data dostawy: [◄] 2026-02-28 [►]       Taryfa: [Tauron G11 ▼]  │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                                                              │  │
│  │  Cena TGE (PLN/MWh)              Koszt całkowity (PLN/kWh)  │  │
│  │  ████████████████████████████   ─────────────────────────── │  │
│  │  500 ┤                    █     0.80 ┤               ▓      │  │
│  │  400 ┤              █████ █     0.70 ┤         ▓▓▓▓▓▓▓▓    │  │
│  │  300 ┤      ████████            0.60 ┤   ▓▓▓▓▓▓             │  │
│  │  200 ┤█████                     0.50 ┤▓▓▓                    │  │
│  │      └──────────────────────         └──────────────────────  │  │
│  │       1  3  5  7  9 11 13 15         1  3  5  7  9 11 13 15  │  │
│  │                                                              │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │  Min         │  │  Średnia     │  │  Max         │            │
│  │  215 PLN/MWh │  │  342 PLN/MWh │  │  521 PLN/MWh │            │
│  │  03:00-04:00 │  │  TGe24       │  │  20:00-21:00 │            │
│  └──────────────┘  └──────────────┘  └──────────────┘            │
│                                                                    │
│  ────────────────────────────────────────────────────────────────  │
│  Historia: [2026-02] [2026-01] [2025-12] ...                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Wykres miesięczny: TGe24 (średnia dobowa)                  │  │
│  │  ████████████████████████████████████████                   │  │
│  └──────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

---

## Specyfikacja widoków

### Widok 1: Ceny dnia (domyślny)

**URL:** `/web/index.html` lub `/web/`

**Elementy:**
- Nawigacja dat: `[◄ poprzedni] [Data dostawy: YYYY-MM-DD] [następny ►]`
  - "Dziś" pokazuje najnowszy dostępny dzień (z `index.json`)
  - Strzałki ◄/► zmieniają datę o ±1 dzień
  - Brak danych dla danej daty = szary przycisk, disabled
- Wybór taryfy: dropdown z listą wszystkich plików z `tariffs/`
  - Format: "Tauron G11", "Tauron G12", "Energa G11", itp.
  - Domyślnie: brak taryfy (pokazuje tylko ceny TGE)
- Wykres godzinowy: słupkowy (bar chart) Chart.js
  - Os X: godziny H01–H24
  - Lewa oś Y: cena TGE w PLN/MWh (kolor niebieski)
  - Prawa oś Y (opcjonalna): koszt całkowity w PLN/kWh (kolor pomarańczowy, widoczny gdy wybrana taryfa)
  - Tooltip po najechaniu: godzina, cena TGE, koszt całkowity
- Karty statystyk:
  - Min: najniższa cena + godzina
  - Średnia: TGe24
  - Max: najwyższa cena + godzina

### Widok 2: Historia

**Elementy:**
- Przełącznik miesiąca: `[◄] 2026-02 [►]`
- Wykres liniowy: oś X = dni miesiąca, oś Y = TGe24 (średnia dobowa PLN/MWh)
- Kliknięcie w punkt otwiera widok 1 dla danego dnia

---

## `web/index.html` — struktura

```html
<!DOCTYPE html>
<html lang="pl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CenyPradu — Ceny energii TGE</title>

  <!-- Tailwind CSS CDN -->
  <script src="https://cdn.tailwindcss.com"></script>

  <!-- Chart.js CDN -->
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>

  <!-- Day.js CDN -->
  <script src="https://cdn.jsdelivr.net/npm/dayjs@1/dayjs.min.js"></script>

  <link rel="stylesheet" href="css/style.css">
</head>
<body class="bg-gray-50 text-gray-900 min-h-screen">

  <!-- Nagłówek -->
  <header class="bg-white shadow-sm">
    <div class="max-w-5xl mx-auto px-4 py-4 flex justify-between items-center">
      <h1 class="text-2xl font-bold text-blue-700">⚡ CenyPradu</h1>
      <nav>
        <button id="btn-day-view" class="px-4 py-2 rounded text-sm font-medium">Dzień</button>
        <button id="btn-month-view" class="px-4 py-2 rounded text-sm font-medium">Historia</button>
      </nav>
    </div>
  </header>

  <!-- Kontrolki -->
  <main class="max-w-5xl mx-auto px-4 py-6">

    <!-- Nawigacja daty -->
    <div class="flex items-center gap-4 mb-6">
      <button id="btn-prev-day" class="px-3 py-2 border rounded hover:bg-gray-100">◄</button>
      <span id="display-date" class="text-xl font-semibold">Ładowanie...</span>
      <button id="btn-next-day" class="px-3 py-2 border rounded hover:bg-gray-100">►</button>
      <button id="btn-today" class="px-4 py-2 bg-blue-600 text-white rounded text-sm">Dziś</button>

      <!-- Wybór taryfy -->
      <select id="tariff-select" class="ml-auto border rounded px-3 py-2 text-sm">
        <option value="">Tylko cena TGE</option>
        <!-- Opcje wypełniane dynamicznie przez JS -->
      </select>
    </div>

    <!-- Wykres godzinowy -->
    <div class="bg-white rounded-lg shadow p-6 mb-6">
      <canvas id="hourly-chart" height="300"></canvas>
    </div>

    <!-- Karty statystyk -->
    <div class="grid grid-cols-3 gap-4 mb-8" id="stats-cards">
      <div class="bg-white rounded-lg shadow p-4 text-center">
        <div class="text-sm text-gray-500 mb-1">Minimum</div>
        <div id="stat-min" class="text-2xl font-bold text-green-600">—</div>
        <div id="stat-min-hour" class="text-xs text-gray-400">—</div>
      </div>
      <div class="bg-white rounded-lg shadow p-4 text-center">
        <div class="text-sm text-gray-500 mb-1">Średnia (TGe24)</div>
        <div id="stat-avg" class="text-2xl font-bold text-blue-600">—</div>
        <div class="text-xs text-gray-400">PLN/MWh</div>
      </div>
      <div class="bg-white rounded-lg shadow p-4 text-center">
        <div class="text-sm text-gray-500 mb-1">Maksimum</div>
        <div id="stat-max" class="text-2xl font-bold text-red-600">—</div>
        <div id="stat-max-hour" class="text-xs text-gray-400">—</div>
      </div>
    </div>

    <!-- Widok historyczny (ukryty domyślnie) -->
    <div id="history-view" class="hidden">
      <div class="flex items-center gap-4 mb-4">
        <button id="btn-prev-month">◄</button>
        <span id="display-month" class="text-lg font-semibold">2026-02</span>
        <button id="btn-next-month">►</button>
      </div>
      <div class="bg-white rounded-lg shadow p-6">
        <canvas id="monthly-chart" height="250"></canvas>
      </div>
    </div>

  </main>

  <footer class="text-center text-sm text-gray-400 py-8">
    Dane: TGE Fixing I | Źródło:
    <a href="https://wyniki.tge.pl/pl/wyniki/rdn/fixing-I/" class="underline" target="_blank">wyniki.tge.pl</a>
    | Aktualizacja codziennie ~11:00
  </footer>

  <script type="module" src="js/app.js"></script>
</body>
</html>
```

---

## `web/js/api.js` — pobieranie danych

```javascript
// Baza URL GitHub Pages — dostosuj do właściwego URL
const BASE_URL = window.location.hostname === "localhost"
  ? "http://localhost:8000"
  : "https://KrzysztofHajdamowicz.github.io/CenyPradu";

/**
 * Pobierz index.json z listą dostępnych dat.
 * @returns {Promise<{dates: string[], latest: string, updated_at: string}>}
 */
export async function fetchIndex() {
  const res = await fetch(`${BASE_URL}/data/prices/index.json`);
  if (!res.ok) throw new Error(`Błąd pobierania index.json: ${res.status}`);
  return res.json();
}

/**
 * Pobierz ceny dla danej daty.
 *
 * Format odpowiedzi:
 * {
 *   "date": "2026-02-28",
 *   "unit": "PLN/MWh",
 *   "prices": [
 *     {"time": "2026-02-28 00:00:00+01:00", "price": 312.50},
 *     {"time": "2026-02-28 01:00:00+01:00", "price": 298.00},
 *     ...
 *   ]
 * }
 *
 * Lista prices jest posortowana rosnąco wg time.
 * Zwykle 24 elementy; 23 przy spring-forward, 25 przy fall-back.
 *
 * @param {string} date - format YYYY-MM-DD
 * @returns {Promise<{date: string, unit: string, prices: Array<{time: string, price: number}>}>}
 */
export async function fetchPrices(date) {
  const res = await fetch(`${BASE_URL}/data/prices/${date}.json`);
  if (!res.ok) throw new Error(`Brak danych dla daty ${date}`);
  return res.json();
}

/**
 * Pomocnik: wyciągnij tablicę samych cen (number[]) z odpowiedzi fetchPrices.
 * Przydatne do obliczeń statystycznych.
 * @param {{prices: Array<{time: string, price: number}>}} pricesData
 * @returns {number[]}
 */
export function extractPriceValues(pricesData) {
  return pricesData.prices.map(p => p.price);
}

/**
 * Pomocnik: wyciągnij etykiety godzin do osi X wykresu.
 * Np. "00:00", "01:00", ..., "23:00"
 * @param {{prices: Array<{time: string, price: number}>}} pricesData
 * @returns {string[]}
 */
export function extractHourLabels(pricesData) {
  return pricesData.prices.map(p => p.time.slice(11, 16));  // "HH:MM"
}

/**
 * Pobierz plik taryfy.
 * @param {string} tariffId - np. "tauron-g11"
 * @returns {Promise<object>}
 */
export async function fetchTariff(tariffId) {
  const res = await fetch(`${BASE_URL}/tariffs/${tariffId}.json`);
  if (!res.ok) throw new Error(`Brak taryfy: ${tariffId}`);
  return res.json();
}

/**
 * Lista dostępnych taryf (GitHub Pages nie obsługuje listowania katalogów).
 */
export const AVAILABLE_TARIFFS = [
  { id: "tauron-g11", label: "Tauron G11" },
  { id: "tauron-g12", label: "Tauron G12" },
  { id: "tauron-g12w", label: "Tauron G12w" },
  { id: "energa-g11", label: "Energa G11" },
  { id: "energa-g12", label: "Energa G12" },
  { id: "energa-g12w", label: "Energa G12w" },
  { id: "enea-g11", label: "Enea G11" },
  { id: "enea-g12", label: "Enea G12" },
  { id: "enea-g12w", label: "Enea G12w" },
  { id: "pge-g11", label: "PGE G11" },
  { id: "pge-g12", label: "PGE G12" },
  { id: "pge-g12w", label: "PGE G12w" },
  { id: "stoen-g11", label: "Stoen G11" },
  { id: "stoen-g12", label: "Stoen G12" },
];
```

---

## `web/js/chart.js` — konfiguracja wykresów

```javascript
/**
 * Renderuj/aktualizuj wykres godzinowy.
 *
 * @param {Chart|null} existingChart - istniejąca instancja Chart.js (lub null)
 * @param {Array<{time: string, price: number}>} pricesData - lista z fetchPrices().prices
 * @param {number[]|null} totalCosts - koszty całkowite w PLN/kWh (lub null, indeksowane jak pricesData)
 * @returns {Chart} - instancja Chart.js
 */
export function renderHourlyChart(existingChart, pricesData, totalCosts = null) {
  const canvas = document.getElementById("hourly-chart");

  // Etykiety osi X: "00:00", "01:00", ... z pola time
  const labels = pricesData.map(p => p.time.slice(11, 16));
  const tgePrices = pricesData.map(p => p.price);

  const datasets = [
    {
      label: "Cena TGE (PLN/MWh)",
      data: tgePrices,
      backgroundColor: "rgba(59, 130, 246, 0.6)",
      borderColor: "rgba(59, 130, 246, 1)",
      borderWidth: 1,
      yAxisID: "yTGE",
    },
  ];

  if (totalCosts) {
    datasets.push({
      label: "Koszt całkowity (PLN/kWh)",
      data: totalCosts,
      backgroundColor: "rgba(249, 115, 22, 0.5)",
      borderColor: "rgba(249, 115, 22, 1)",
      borderWidth: 1,
      yAxisID: "yTotal",
      type: "line",
    });
  }

  const config = {
    type: "bar",
    data: { labels, datasets },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { position: "top" },
        tooltip: {
          callbacks: {
            title: (items) => {
              // Pokaż pełny timestamp w tooltip
              return pricesData[items[0].dataIndex].time;
            },
            label: (ctx) => {
              if (ctx.dataset.yAxisID === "yTGE") {
                return `TGE: ${ctx.parsed.y.toFixed(2)} PLN/MWh`;
              }
              return `Całkowity: ${ctx.parsed.y.toFixed(4)} PLN/kWh`;
            },
          },
        },
      },
      scales: {
        yTGE: {
          type: "linear",
          position: "left",
          title: { display: true, text: "PLN/MWh" },
        },
        ...(totalCosts ? {
          yTotal: {
            type: "linear",
            position: "right",
            title: { display: true, text: "PLN/kWh" },
            grid: { drawOnChartArea: false },
          },
        } : {}),
      },
    },
  };

  if (existingChart) {
    existingChart.data = config.data;
    existingChart.options = config.options;
    existingChart.update();
    return existingChart;
  }

  return new Chart(canvas, config);
}

/**
 * Renderuj wykres miesięczny (TGe24 — średnia dobowa).
 *
 * @param {Chart|null} existingChart
 * @param {Array<{date: string, prices: Array<{time: string, price: number}>}>} datesWithPrices
 */
export function renderMonthlyChart(existingChart, datesWithPrices) {
  const canvas = document.getElementById("monthly-chart");
  const labels = datesWithPrices.map(d => d.date);
  const avgs = datesWithPrices.map(d => {
    const vals = d.prices.map(p => p.price);
    return (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2);
  });

  const config = {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: "TGe24 (PLN/MWh)",
        data: avgs,
        borderColor: "rgba(59, 130, 246, 1)",
        backgroundColor: "rgba(59, 130, 246, 0.1)",
        fill: true,
        tension: 0.3,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { position: "top" } },
      scales: {
        y: { title: { display: true, text: "PLN/MWh" } },
      },
      onClick: (evt, elements) => {
        if (elements.length > 0) {
          const idx = elements[0].index;
          canvas.dispatchEvent(new CustomEvent("day-selected", {
            detail: { date: labels[idx] },
            bubbles: true,
          }));
        }
      },
    },
  };

  if (existingChart) {
    existingChart.data = config.data;
    existingChart.update();
    return existingChart;
  }

  return new Chart(canvas, config);
}
```

---

## `web/js/app.js` — logika aplikacji

```javascript
import { fetchIndex, fetchPrices, fetchTariff, AVAILABLE_TARIFFS } from "./api.js";
import { renderHourlyChart, renderMonthlyChart } from "./chart.js";
import { calculateHourlyCostNetto } from "./tariffs.js";
import { isPolishHoliday } from "./holidays.js";

// State
let state = {
  index: null,         // index.json
  currentDate: null,   // YYYY-MM-DD
  currentPrices: null, // {date, prices: [{time, price}, ...]}
  currentTariff: null, // tariff object lub null
  hourlyChart: null,
  monthlyChart: null,
  view: "day",         // "day" | "month"
  currentMonth: null,  // "YYYY-MM"
};

// Inicjalizacja
async function init() {
  const tariffSelect = document.getElementById("tariff-select");
  AVAILABLE_TARIFFS.forEach(t => {
    const opt = document.createElement("option");
    opt.value = t.id;
    opt.textContent = t.label;
    tariffSelect.appendChild(opt);
  });

  state.index = await fetchIndex();
  state.currentDate = state.index.latest;
  state.currentMonth = state.currentDate.slice(0, 7);

  await loadDayView(state.currentDate);

  document.getElementById("btn-prev-day").addEventListener("click", () => navigateDay(-1));
  document.getElementById("btn-next-day").addEventListener("click", () => navigateDay(+1));
  document.getElementById("btn-today").addEventListener("click", () => loadDayView(state.index.latest));
  document.getElementById("btn-day-view").addEventListener("click", () => setView("day"));
  document.getElementById("btn-month-view").addEventListener("click", () => setView("month"));
  tariffSelect.addEventListener("change", () => onTariffChange(tariffSelect.value));
}

async function loadDayView(date) {
  state.currentDate = date;
  document.getElementById("display-date").textContent = date;

  try {
    state.currentPrices = await fetchPrices(date);
  } catch (e) {
    console.error(e);
    document.getElementById("display-date").textContent = `${date} — brak danych`;
    return;
  }

  updateStats(state.currentPrices.prices);
  renderHourlyWithTariff();
}

function renderHourlyWithTariff() {
  const pricesData = state.currentPrices.prices;  // [{time, price}, ...]
  let totalCosts = null;

  if (state.currentTariff) {
    totalCosts = pricesData.map(({ time, price }) => {
      // Wyciągnij datę i godzinę z timestampa
      const localDate = new Date(time.replace(" ", "T"));
      const dayType = getDayType(state.currentPrices.date, localDate);
      const wallHour = localDate.getHours();  // 0-23
      return calculateHourlyCostNetto(price, wallHour, dayType, state.currentTariff);
    });
  }

  state.hourlyChart = renderHourlyChart(state.hourlyChart, pricesData, totalCosts);
}

function updateStats(pricesData) {
  // pricesData = [{time: "...", price: ...}, ...]
  const values = pricesData.map(p => p.price);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const avg = values.reduce((a, b) => a + b, 0) / values.length;

  const minItem = pricesData[values.indexOf(min)];
  const maxItem = pricesData[values.indexOf(max)];

  document.getElementById("stat-min").textContent = `${min.toFixed(2)} PLN/MWh`;
  document.getElementById("stat-min-hour").textContent = minItem.time.slice(11, 16);
  document.getElementById("stat-avg").textContent = `${avg.toFixed(2)} PLN/MWh`;
  document.getElementById("stat-max").textContent = `${max.toFixed(2)} PLN/MWh`;
  document.getElementById("stat-max-hour").textContent = maxItem.time.slice(11, 16);
}

async function onTariffChange(tariffId) {
  if (!tariffId) {
    state.currentTariff = null;
  } else {
    try {
      state.currentTariff = await fetchTariff(tariffId);
    } catch (e) {
      console.error(`Błąd ładowania taryfy ${tariffId}:`, e);
      state.currentTariff = null;
    }
  }
  if (state.currentPrices) renderHourlyWithTariff();
}

/**
 * Wyznacz typ dnia dla kalkulatora taryf.
 * @param {string} dateStr - YYYY-MM-DD (data dostawy, ważna dla logiki świąt)
 * @param {Date} localDate - obiekt Date z lokalnym timestampem godziny
 */
function getDayType(dateStr, localDate) {
  if (isPolishHoliday(dateStr)) return "holiday";
  const dow = localDate.getDay();  // 0=niedziela, 6=sobota
  if (dow === 0) return "sunday";
  if (dow === 6) return "saturday";
  return "weekday";
}

function navigateDay(delta) {
  const dates = state.index.dates;
  const idx = dates.indexOf(state.currentDate);
  const newIdx = idx + delta;
  if (newIdx >= 0 && newIdx < dates.length) {
    loadDayView(dates[newIdx]);
  }
}

function setView(view) {
  state.view = view;
  document.getElementById("history-view").classList.toggle("hidden", view !== "month");
  if (view === "month") loadMonthView(state.currentMonth);
}

async function loadMonthView(month) {
  state.currentMonth = month;
  document.getElementById("display-month").textContent = month;

  const datesInMonth = state.index.dates.filter(d => d.startsWith(month));
  // Pobierz ceny równolegle
  const datesWithPrices = await Promise.all(
    datesInMonth.map(date =>
      fetchPrices(date).then(p => ({ date, prices: p.prices }))
    )
  );

  state.monthlyChart = renderMonthlyChart(state.monthlyChart, datesWithPrices);
}

// Start
init().catch(console.error);
```

---

## Responsywność i UX

- Layout mobilny: karty statystyk w kolumnie, wykres full-width
- Obsługa błędów: szara karta "Brak danych" zamiast pustego wykresu
- Loading state: spinner lub skeleton podczas ładowania
- Tooltip na wykresie: pokazuj godzinę, cenę TGE i (jeśli wybrana taryfa) koszt całkowity
- Klawiszowa nawigacja: `←` / `→` do poprzedniego/następnego dnia

---

## Lokalny development

```bash
# Prosty serwer HTTP do testowania
cd /path/to/CenyPradu
python -m http.server 8000
# Otwórz: http://localhost:8000/web/
```

Plik `api.js` wykrywa `localhost` i zmienia base URL.

---

## SEO i meta tagi

```html
<meta name="description" content="Godzinowe ceny energii elektrycznej TGE Fixing I — aktualne i historyczne. Kalkulator kosztów z taryfami dystrybucji.">
<meta property="og:title" content="CenyPradu — Ceny energii TGE">
<meta property="og:description" content="Godzinowe ceny TGE z kalkulatorem taryf dystrybucji">
```

---

## Definition of Done

- [ ] `web/index.html` wyświetla wykres godzinowy dla najnowszego dnia
- [ ] Nawigacja ◄/► między dniami działa poprawnie
- [ ] Dropdown taryf ładuje się dynamicznie z listy `AVAILABLE_TARIFFS`
- [ ] Po wybraniu taryfy wykres pokazuje drugi dataset (koszt całkowity PLN/kWh)
- [ ] Karty statystyk (min/avg/max) aktualizują się po zmianie dnia
- [ ] Widok historyczny pokazuje TGe24 dla wybranego miesiąca
- [ ] Kliknięcie w punkt wykresu miesięcznego nawiguje do widoku dziennego
- [ ] Strona działa lokalnie przez `python -m http.server`
- [ ] Strona działa na GitHub Pages (właściwy BASE_URL)
- [ ] Layout responsywny na mobile (min. 375px)
- [ ] Brak błędów w konsoli przeglądarki
