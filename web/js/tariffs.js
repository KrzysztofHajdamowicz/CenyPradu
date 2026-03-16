/**
 * tariffs.js — kalkulator kosztu energii z uwzględnieniem taryfy dystrybucyjnej.
 *
 * Eksportuje:
 *   calculateHourlyCostNetto(spotPricePLNperMWh, wallHour, dayOfWeek, tariff, month?) → PLN/kWh
 *   calculateHourlyCostBrutto(spotPricePLNperMWh, wallHour, dayOfWeek, tariff, month?) → PLN/kWh
 *   getDistributionRate(wallHour, dayOfWeek, tariff, month?) → PLN/kWh
 *   loadTariff(tariffId) → Promise<object>
 *   listAvailableTariffs() → Array<{id, name, dso, tariff_group}>
 *
 * Parametr `month` (1–12) jest wymagany dla taryf sezonowych (seasonal: true),
 * tj. G13, G13s, G13active. Dla taryf niesezonowych jest ignorowany.
 */

/** Katalog dostępnych taryf – uzupełnij przy dodaniu nowych plików. */
export const AVAILABLE_TARIFFS = [
  { id: "tauron-g11",      name: "Tauron G11",       dso: "TAURON Dystrybucja S.A.",    tariff_group: "G11" },
  { id: "tauron-g12",      name: "Tauron G12",       dso: "TAURON Dystrybucja S.A.",    tariff_group: "G12" },
  { id: "tauron-g12w",     name: "Tauron G12w",      dso: "TAURON Dystrybucja S.A.",    tariff_group: "G12w" },
  { id: "tauron-g13",      name: "Tauron G13",       dso: "TAURON Dystrybucja S.A.",    tariff_group: "G13" },
  { id: "tauron-g13s",     name: "Tauron G13s",      dso: "TAURON Dystrybucja S.A.",    tariff_group: "G13s" },
  { id: "energa-g11",      name: "Energa G11",       dso: "Energa-Operator S.A.",       tariff_group: "G11" },
  { id: "energa-g12",      name: "Energa G12",       dso: "Energa-Operator S.A.",       tariff_group: "G12" },
  { id: "energa-g12w",     name: "Energa G12w",      dso: "Energa-Operator S.A.",       tariff_group: "G12w" },
  { id: "enea-g11",        name: "Enea G11",         dso: "ENEA Operator Sp. z o.o.",   tariff_group: "G11" },
  { id: "enea-g12",        name: "Enea G12",         dso: "ENEA Operator Sp. z o.o.",   tariff_group: "G12" },
  { id: "enea-g12w",       name: "Enea G12w",        dso: "ENEA Operator Sp. z o.o.",   tariff_group: "G12w" },
  { id: "enea-g13active",  name: "Enea G13active",   dso: "ENEA Operator Sp. z o.o.",   tariff_group: "G13active" },
  { id: "pge-g11",         name: "PGE G11",          dso: "PGE Dystrybucja S.A.",       tariff_group: "G11" },
  { id: "pge-g12",         name: "PGE G12",          dso: "PGE Dystrybucja S.A.",       tariff_group: "G12" },
  { id: "pge-g12w",        name: "PGE G12w",         dso: "PGE Dystrybucja S.A.",       tariff_group: "G12w" },
  { id: "stoen-g11",       name: "Stoen G11",        dso: "Stoen Operator Sp. z o.o.",  tariff_group: "G11" },
  { id: "stoen-g12",       name: "Stoen G12",        dso: "Stoen Operator Sp. z o.o.",  tariff_group: "G12" },
];

/**
 * Wczytuje plik taryfy z katalogu /tariffs/.
 * @param {string} tariffId - identyfikator taryfy, np. "tauron-g11"
 * @returns {Promise<object>} obiekt taryfy
 */
export async function loadTariff(tariffId) {
  const baseUrl = getBaseUrl();
  const url = `${baseUrl}data/tariffs/${tariffId}.json`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Nie można wczytać taryfy "${tariffId}": HTTP ${response.status}`);
  }
  return response.json();
}

/**
 * Zwraca listę dostępnych taryf z metadanymi.
 * @returns {Array<{id, name, dso, tariff_group}>}
 */
export function listAvailableTariffs() {
  return AVAILABLE_TARIFFS;
}

/**
 * Oblicza całkowity koszt energii netto (bez VAT) w PLN/kWh dla danej godziny.
 *
 * @param {number} spotPricePLNperMWh - cena TGE Fixing I dla danej godziny [PLN/MWh]
 * @param {number} wallHour - godzina zegarowa 0–23 (0 = 00:00–01:00, 23 = 23:00–24:00)
 * @param {string} dayOfWeek - "weekday" | "saturday" | "sunday" | "holiday"
 * @param {object} tariff - obiekt taryfy wczytany z JSON
 * @param {number} [month] - miesiąc 1–12, wymagany dla taryf sezonowych (G13, G13s, G13active)
 * @returns {number} całkowity koszt netto w PLN/kWh
 */
export function calculateHourlyCostNetto(spotPricePLNperMWh, wallHour, dayOfWeek, tariff, month) {
  const spotPLNkWh = spotPricePLNperMWh / 1000;

  const distributionRate = getDistributionRate(wallHour, dayOfWeek, tariff, month);

  const systemCharges = Object.values(tariff.system_charges_pln_kwh).reduce(
    (sum, v) => sum + v,
    0,
  );

  return spotPLNkWh + distributionRate + systemCharges + tariff.excise_pln_kwh;
}

/**
 * Oblicza całkowity koszt energii brutto (z VAT) w PLN/kWh dla danej godziny.
 *
 * @param {number} spotPricePLNperMWh - cena TGE Fixing I [PLN/MWh]
 * @param {number} wallHour - godzina zegarowa 0–23
 * @param {string} dayOfWeek - "weekday" | "saturday" | "sunday" | "holiday"
 * @param {object} tariff - obiekt taryfy
 * @param {number} [month] - miesiąc 1–12, wymagany dla taryf sezonowych
 * @returns {number} całkowity koszt brutto w PLN/kWh
 */
export function calculateHourlyCostBrutto(spotPricePLNperMWh, wallHour, dayOfWeek, tariff, month) {
  return (
    calculateHourlyCostNetto(spotPricePLNperMWh, wallHour, dayOfWeek, tariff, month) *
    (1 + tariff.vat_rate)
  );
}

/**
 * Wyznacza zmienną stawkę dystrybucyjną (składnik zmienny stawki sieciowej) dla danej godziny.
 *
 * @param {number} wallHour - godzina zegarowa 0–23
 * @param {string} dayOfWeek - "weekday" | "saturday" | "sunday" | "holiday"
 * @param {object} tariff - obiekt taryfy
 * @param {number} [month] - miesiąc 1–12, wymagany gdy tariff.variable_rates_pln_kwh.seasonal === true
 * @returns {number} stawka dystrybucyjna w PLN/kWh
 */
export function getDistributionRate(wallHour, dayOfWeek, tariff, month) {
  const rates = tariff.variable_rates_pln_kwh;

  if (rates.type === "flat") {
    return rates.rate;
  }

  if (rates.type === "tou") {
    const periods = resolveSeasonalPeriods(rates, month, tariff.id);
    const resolvedDay = ["weekday", "saturday", "sunday", "holiday"].includes(dayOfWeek)
      ? dayOfWeek
      : "weekday";

    for (const period of periods) {
      const schedule = period.schedule[resolvedDay] ?? [];
      if (isInSchedule(wallHour, schedule)) {
        return period.rate;
      }
    }
    throw new Error(
      `Brak stawki dla godziny ${wallHour}, dzień "${dayOfWeek}"` +
        (month != null ? `, miesiąc ${month}` : "") +
        ` w taryfie "${tariff.id}"`,
    );
  }

  throw new Error(`Nieznany typ stawki: "${rates.type}" w taryfie "${tariff.id}"`);
}

/**
 * Zwraca tablicę periods dla aktualnego sezonu, obsługując zarówno taryfy
 * sezonowe (seasonal: true → lookup w seasons[]) jak i zwykłe (periods[]).
 */
function resolveSeasonalPeriods(rates, month, tariffId) {
  if (!rates.seasonal) {
    return rates.periods;
  }

  if (month == null || month < 1 || month > 12) {
    throw new Error(
      `Taryfa "${tariffId}" jest sezonowa — wymagany parametr month (1–12), otrzymano: ${month}`,
    );
  }

  for (const season of rates.seasons) {
    if (season.months.includes(month)) {
      return season.periods;
    }
  }

  throw new Error(
    `Brak sezonu dla miesiąca ${month} w taryfie "${tariffId}"`,
  );
}

/**
 * Sprawdza, czy godzina zegarowa (0–23) należy do któregoś z przedziałów w schedule.
 *
 * Przedziały w formacie "HH:MM-HH:MM", np. ["06:00-13:00", "15:00-22:00"].
 * Konwencja: wallHour=6 oznacza godzinę 06:00–07:00, wallHour=22 = 22:00–23:00 itd.
 * "00:00-24:00" → cała doba.
 *
 * @param {number} wallHour - liczba całkowita 0–23
 * @param {string[]} schedule - lista przedziałów
 * @returns {boolean}
 */
function isInSchedule(wallHour, schedule) {
  for (const range of schedule) {
    const [startStr, endStr] = range.split("-");
    const start = parseInt(startStr.split(":")[0], 10);
    const end   = parseInt(endStr.split(":")[0], 10);

    if (start === 0 && end === 24) {
      // "00:00-24:00" – cała doba
      return true;
    }

    if (start < end) {
      // Normalny przedział: 06:00-13:00 → godziny 6,7,...,12
      if (wallHour >= start && wallHour < end) return true;
    } else if (start > end) {
      // Przedział przez północ: 22:00-06:00 → godziny 22,23,0,1,2,3,4,5
      if (wallHour >= start || wallHour < end) return true;
    }
  }
  return false;
}

/**
 * Oblicza typ dnia tygodnia dla daty wejściowej z uwzględnieniem polskich świąt.
 *
 * @param {Date} date - obiekt daty (czas lokalny PL)
 * @returns {"weekday"|"saturday"|"sunday"|"holiday"}
 */
export function getDayType(date) {
  // Leniwy import holidays, by uniknąć cyklicznych zależności
  if (typeof isPolishHoliday === "undefined") {
    // W środowisku bez modułów – fallback do dnia tygodnia
  }
  const dow = date.getDay(); // 0=niedz, 6=sob
  if (typeof window !== "undefined" && window._isPolishHoliday) {
    if (window._isPolishHoliday(date)) return "holiday";
  }
  if (dow === 0) return "sunday";
  if (dow === 6) return "saturday";
  return "weekday";
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Zwraca bazowy URL repozytorium (GitHub Pages lub lokalny).
 * Działa zarówno w przeglądarce, jak i w testach Node.
 */
function getBaseUrl() {
  if (typeof window === "undefined") return "";
  const path = window.location.pathname;
  // Na GitHub Pages ścieżka zaczyna się od /CenyPradu/
  const match = path.match(/^(\/[^/]+\/)/);
  return match ? match[1] : "/";
}
