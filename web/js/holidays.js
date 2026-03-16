/**
 * holidays.js — Polskie święta ustawowe.
 *
 * Eksportuje:
 *   isPolishHoliday(date) → boolean
 *   getPolishHolidays(year) → Date[]
 */

/**
 * Stałe święta ustawowe (MM-DD), niezależne od roku.
 * Źródło: Ustawa z dnia 18 stycznia 1951 r. o dniach wolnych od pracy (Dz.U. z 2015 r. poz. 90 ze zm.)
 */
const FIXED_HOLIDAYS = [
  "01-01", // Nowy Rok
  "05-01", // Święto Pracy
  "05-03", // Konstytucja 3 Maja
  "08-15", // Wniebowzięcie NMP
  "11-01", // Wszystkich Świętych
  "11-11", // Dzień Niepodległości
  "12-25", // Boże Narodzenie
  "12-26", // Drugi Dzień Bożego Narodzenia
];

/**
 * Oblicza datę Niedzieli Wielkanocnej dla danego roku algorytmem Anonymous Gregorian (Meeus/Jones/Butcher).
 * @param {number} year
 * @returns {Date}
 */
function calculateEasterDate(year) {
  const a = year % 19;
  const b = Math.floor(year / 100);
  const c = year % 100;
  const d = Math.floor(b / 4);
  const e = b % 4;
  const f = Math.floor((b + 8) / 25);
  const g = Math.floor((b - f + 1) / 3);
  const h = (19 * a + b - d - g + 15) % 30;
  const i = Math.floor(c / 4);
  const k = c % 4;
  const l = (32 + 2 * e + 2 * i - h - k) % 7;
  const m = Math.floor((a + 11 * h + 22 * l) / 451);
  const month = Math.floor((h + l - 7 * m + 114) / 31);
  const day   = ((h + l - 7 * m + 114) % 31) + 1;
  return new Date(year, month - 1, day);
}

/**
 * Dodaje określoną liczbę dni do daty.
 * @param {Date} date
 * @param {number} days
 * @returns {Date}
 */
function addDays(date, days) {
  const result = new Date(date);
  result.setDate(result.getDate() + days);
  return result;
}

/**
 * Zwraca listę ruchomych świąt ustawowych dla danego roku.
 * @param {number} year
 * @returns {Date[]}
 */
function getMovableHolidays(year) {
  const easter = calculateEasterDate(year);
  return [
    easter,               // Niedziela Wielkanocna
    addDays(easter, 1),   // Poniedziałek Wielkanocny
    addDays(easter, 49),  // Zielone Świątki (Niedziela Zesłania Ducha Świętego)
    addDays(easter, 60),  // Boże Ciało (Corpus Christi)
  ];
}

/**
 * Zwraca pełną listę polskich świąt ustawowych dla danego roku.
 * @param {number} year
 * @returns {Date[]}
 */
export function getPolishHolidays(year) {
  const fixed = FIXED_HOLIDAYS.map((mmdd) => {
    const [month, day] = mmdd.split("-").map(Number);
    return new Date(year, month - 1, day);
  });
  const movable = getMovableHolidays(year);
  return [...fixed, ...movable].sort((a, b) => a - b);
}

/**
 * Sprawdza, czy dana data jest polskim świętem ustawowym.
 * Porównanie odbywa się na podstawie roku, miesiąca i dnia (bez godziny).
 *
 * @param {Date} date
 * @returns {boolean}
 */
export function isPolishHoliday(date) {
  const year  = date.getFullYear();
  const month = date.getMonth();
  const day   = date.getDate();

  const holidays = getPolishHolidays(year);
  return holidays.some(
    (h) => h.getFullYear() === year && h.getMonth() === month && h.getDate() === day,
  );
}

/**
 * Rejestruje funkcję isPolishHoliday globalnie, by tariffs.js mógł ją używać.
 * Wywołaj w HTML przed załadowaniem tariffs.js.
 */
export function registerGlobalHolidayCheck() {
  if (typeof window !== "undefined") {
    window._isPolishHoliday = isPolishHoliday;
  }
}

// ---------------------------------------------------------------------------
// Weryfikacja – można uruchomić w DevTools
// ---------------------------------------------------------------------------

if (typeof window !== "undefined" && window.location.search.includes("debug-holidays")) {
  const year = new Date().getFullYear();
  console.table(
    getPolishHolidays(year).map((d) => ({
      data: d.toLocaleDateString("pl-PL"),
      dzień: d.toLocaleDateString("pl-PL", { weekday: "long" }),
    })),
  );
}
