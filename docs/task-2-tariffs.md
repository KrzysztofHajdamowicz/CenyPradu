# Zadanie 2: Katalog taryf dystrybucyjnych

## Cel

Stworzenie katalogu plików JSON opisujących taryfy dystrybucji energii elektrycznej największych Operatorów Systemu Dystrybucyjnego (OSD) w Polsce. Pliki posłużą frontendowi (Faza 3) do obliczenia całkowitego kosztu energii dla użytkownika końcowego.

## Kontekst

Cena energii dla odbiorcy końcowego składa się z wielu składników:

```
Cena całkowita = cena sprzedaży + dystrybucja + opłaty systemowe + VAT

Cena sprzedaży:
  • Dla taryf statycznych: stała cena zbiorcza od sprzedawcy
  • Dla taryf dynamicznych (cena TGE): Fixing I PLN/MWh ÷ 1000 = PLN/kWh

Opłaty dystrybucyjne (zmienne, za kWh):
  • Opłata zmienna sieciowa (OZS) — zależna od grupy taryfowej i pory doby
  • Opłata jakościowa
  • Opłata mocowa (od 2021)
  • Opłata OZE

Opłaty systemowe (stałe, za kW mocy lub ryczałt miesięczny):
  • Opłata stała sieciowa (OSS)
  • Opłata abonamentowa / opłata handlowa

Inne:
  • Akcyza: 5,00 PLN/MWh = 0,005 PLN/kWh (zwolnienie dla ≤10 kWh/h)
  • VAT: 23% od całości
```

---

## OSD do pokrycia (priorytet)

| OSD                           | Region                                                    | Taryfy         |
| ----------------------------- | --------------------------------------------------------- | -------------- |
| **Tauron Dystrybucja S.A.**   | Śląsk, Małopolska, Dolny Śląsk, Opolskie, Podkarpacie     | G11, G12, G12w |
| **Energa-Operator S.A.**      | Pomorze, Warmia-Mazury, Kujawsko-Pomorskie, part Mazowsza | G11, G12, G12w |
| **Enea Operator Sp. z o.o.**  | Wielkopolska, Kujawy, Lubuskie, Zachodniopomorskie        | G11, G12, G12w |
| **PGE Dystrybucja S.A.**      | Mazowsze, Łódź, Lublin, Podkarpacie, Rzeszów              | G11, G12, G12w |
| **Stoen Operator Sp. z o.o.** | Warszawa (obszar miejski)                                 | G11, G12       |

---

## Grupy taryfowe

### G11 — Taryfa jednoprzedziałowa (flat rate)

- Ta sama stawka przez całą dobę, wszystkie dni tygodnia
- Prosta, bez stref czasowych

### G12 — Taryfa dwuprzedziałowa (day/night)

Dwie strefy:

- **Dzienna:** zazwyczaj 06:00–21:00 (pon–sob) lub 06:00–13:00 + 15:00–22:00
- **Nocna:** reszta doby + niedziele/święta

Dokładne godziny różnią się między OSD — weryfikuj w obowiązującej taryfie.

### G12w — Taryfa trzyprzedziałowa (peak/shoulder/night)

Trzy strefy. Przykład (do weryfikacji):

- **Szczyt:** 07:00–13:00 i 15:00–21:00 (dni robocze)
- **Poza szczytem (off-peak):** 13:00–15:00 i 21:00–22:00 (dni robocze)
- **Noc:** 22:00–07:00 + weekendy + święta

### G13 — Taryfa trójstrefowa sezonowa (Tauron)

Trzy strefy z różnym harmonogramem w zależności od sezonu (lato/zima). Stawki identyczne w obu sezonach:

- **Szczyt przedpołudniowy:** 07:00–13:00 (cały rok)
- **Szczyt popołudniowy:** 19:00–22:00 (lato) / 16:00–21:00 (zima)
- **Pozostałe godziny doby:** reszta + weekendy/święta = cała doba

Lato: kwiecień–wrzesień, zima: październik–marzec.

### G13s — Taryfa trójstrefowa sezonowa z różnicowaniem stawek (Tauron)

Trzy strefy z harmonogramem i stawkami zmiennymi wg sezonu ORAZ typu dnia (roboczy / wolny):

- **Dzienna szczytowa:** różne godziny lato/zima, różne stawki roboczy/wolny
- **Dzienna pozaszczytowa:** analogicznie
- **Nocna:** 21:00–07:00, stała stawka niezależnie od sezonu/dnia

Dostępna wyłącznie u Tauron Dystrybucja.

### G13active — Taryfa trójstrefowa miesięczna (Enea)

Trzy strefy ze zmiennym harmonogramem co miesiąc, powiązane z profilem produkcji OZE:

- **Strefa zalecanego poboru:** najtańsza (zachęta do zużycia w godzinach nadwyżki OZE)
- **Strefa zalecanego ograniczania:** najdroższa (szczyty obciążenia sieci)
- **Pozostałe godziny doby:** stawka standardowa

Stawki jednakowe cały rok — zmienia się tylko harmonogram stref. Dostępna u Enea Operator.

---

## Format JSON taryfy

### Schemat pliku `tariffs/OPERATOR-TARIFA.json`

```json
{
  "id": "tauron-g11-2025",
  "name": "Tauron Dystrybucja — Taryfa G11",
  "dso": "Tauron Dystrybucja S.A.",
  "tariff_group": "G11",
  "valid_from": "2025-01-01",
  "valid_to": null,
  "version": "2025",
  "currency": "PLN",
  "source_url": "https://www.tauron-dystrybucja.pl/taryfy",

  "variable_rates_pln_kwh": {
    "type": "flat",
    "rate": 0.2456
  },

  "fixed_charges_monthly": {
    "subscription_pln": 10.32,
    "power_demand_pln_per_kw": 0.0
  },

  "system_charges_pln_kwh": {
    "oze": 0.0001,
    "capacity": 0.015,
    "quality": 0.0016,
    "transition": 0.0001,
    "cogeneration": 0.0
  },

  "excise_pln_kwh": 0.005,

  "vat_rate": 0.23
}
```

### Schemat dla G12 (taryfa dwuprzedziałowa)

```json
{
  "id": "tauron-g12-2025",
  "name": "Tauron Dystrybucja — Taryfa G12",
  "dso": "Tauron Dystrybucja S.A.",
  "tariff_group": "G12",
  "valid_from": "2025-01-01",
  "valid_to": null,
  "version": "2025",
  "currency": "PLN",
  "source_url": "https://www.tauron-dystrybucja.pl/taryfy",

  "variable_rates_pln_kwh": {
    "type": "tou",
    "periods": [
      {
        "name": "day",
        "label": "Dzienna",
        "rate": 0.3123,
        "schedule": {
          "weekdays": ["06:00-21:00"],
          "saturday": ["06:00-21:00"],
          "sunday": [],
          "holidays": []
        }
      },
      {
        "name": "night",
        "label": "Nocna",
        "rate": 0.1456,
        "schedule": {
          "weekdays": ["00:00-06:00", "21:00-24:00"],
          "saturday": ["00:00-06:00", "21:00-24:00"],
          "sunday": ["00:00-24:00"],
          "holidays": ["00:00-24:00"]
        }
      }
    ]
  },

  "fixed_charges_monthly": {
    "subscription_pln": 10.32,
    "power_demand_pln_per_kw": 0.0
  },

  "system_charges_pln_kwh": {
    "oze": 0.0001,
    "capacity": 0.015,
    "quality": 0.0016,
    "transition": 0.0001,
    "cogeneration": 0.0
  },

  "excise_pln_kwh": 0.005,

  "vat_rate": 0.23
}
```

### Schemat dla G13 / G13s / G13active (taryfa sezonowa)

Taryfy sezonowe używają pola `seasonal: true` i tablicy `seasons` zamiast `periods`:

```json
{
  "variable_rates_pln_kwh": {
    "type": "tou",
    "seasonal": true,
    "seasons": [
      {
        "name": "summer",
        "label": "Lato (kwiecień–wrzesień)",
        "months": [4, 5, 6, 7, 8, 9],
        "periods": [
          {
            "name": "morning_peak",
            "label": "Szczyt przedpołudniowy",
            "rate": 0.2203,
            "schedule": {
              "weekday": ["07:00-13:00"],
              "saturday": [],
              "sunday": [],
              "holiday": []
            }
          }
        ]
      },
      {
        "name": "winter",
        "label": "Zima (październik–marzec)",
        "months": [1, 2, 3, 10, 11, 12],
        "periods": []
      }
    ]
  }
}
```

Kalkulator wymaga dodatkowego parametru `month` (1–12) dla taryf sezonowych.

### Konwencja `schedule`

- Godziny w formacie `"HH:MM-HH:MM"` (czas lokalny Polski)
- `"00:00-24:00"` oznacza całą dobę
- Puste tablice `[]` oznaczają, że dana strefa nie obowiązuje w ten dzień
- Suma stref dla każdego dnia musi pokrywać całą dobę (00:00-24:00)
- Święta polskie traktowane jak niedziele (w większości taryf G12)

---

## Logika kalkulatora (JavaScript)

Funkcja `calculateHourlyCostNetto(spotPricePLNperMWh, wallHour, dayOfWeek, tariff, month?)` zwraca całkowity koszt w PLN/kWh.

Parametr `month` (1–12) jest wymagany dla taryf sezonowych (`seasonal: true`). Dla taryf G11/G12/G12w jest opcjonalny.

**Konwencja parametru `wallHour`:** liczba całkowita 0–23 (0 = godzina 00:00–01:00).
Pochodzi bezpośrednio z `new Date(priceEntry.time.replace(" ", "T")).getHours()`.

```javascript
/**
 * @param {number} spotPricePLNperMWh - cena TGE Fixing I dla danej godziny
 * @param {number} wallHour - godzina zegarowa (0-23), np. 0=00:00-01:00, 23=23:00-24:00
 * @param {string} dayOfWeek - "weekday" | "saturday" | "sunday" | "holiday"
 * @param {object} tariff - obiekt taryfy wczytany z JSON
 * @returns {number} koszt całkowity w PLN/kWh (netto bez VAT)
 */
export function calculateHourlyCostNetto(
  spotPricePLNperMWh,
  wallHour,
  dayOfWeek,
  tariff,
) {
  const spotPLNkWh = spotPricePLNperMWh / 1000;

  const distributionRate = getDistributionRate(wallHour, dayOfWeek, tariff);

  const systemCharges = Object.values(tariff.system_charges_pln_kwh).reduce(
    (sum, v) => sum + v,
    0,
  );

  return spotPLNkWh + distributionRate + systemCharges + tariff.excise_pln_kwh;
}

export function calculateHourlyCostBrutto(
  spotPricePLNperMWh,
  wallHour,
  dayOfWeek,
  tariff,
) {
  return (
    calculateHourlyCostNetto(spotPricePLNperMWh, wallHour, dayOfWeek, tariff) *
    (1 + tariff.vat_rate)
  );
}

/**
 * Wyznacz zmienną stawkę dystrybucyjną dla danej godziny zegarowej.
 * @param {number} wallHour - 0-23
 */
function getDistributionRate(wallHour, dayOfWeek, tariff) {
  const rates = tariff.variable_rates_pln_kwh;

  if (rates.type === "flat") {
    return rates.rate;
  }

  if (rates.type === "tou") {
    for (const period of rates.periods) {
      const scheduleKey = ["weekday", "saturday", "sunday", "holiday"].includes(
        dayOfWeek,
      )
        ? dayOfWeek
        : "weekday";
      const schedule = period.schedule[scheduleKey] ?? [];
      if (isInSchedule(wallHour, schedule)) {
        return period.rate;
      }
    }
    throw new Error(`Brak stawki dla godziny ${wallHour}, dzień ${dayOfWeek}`);
  }

  throw new Error(`Nieznany typ stawki: ${rates.type}`);
}

/**
 * Sprawdź czy godzina zegarowa (0-23) należy do przedziałów w schedule.
 * Przedziały w formacie ["HH:MM-HH:MM", ...] np. ["06:00-21:00"]
 *
 * @param {number} wallHour - 0-23
 * @param {string[]} schedule - lista przedziałów, np. ["06:00-21:00", "13:00-15:00"]
 */
function isInSchedule(wallHour, schedule) {
  for (const range of schedule) {
    const [startStr, endStr] = range.split("-");
    const start = parseInt(startStr.split(":")[0]); // "06:00" → 6
    const end = parseInt(endStr.split(":")[0]); // "21:00" → 21

    if (start < end) {
      // Normalny przedział: np. 06:00-21:00 → godz 6,7,...,20
      if (wallHour >= start && wallHour < end) return true;
    } else if (start > end) {
      // Przedział przez północ: np. 21:00-06:00 → godz 21,22,23,0,1,2,3,4,5
      if (wallHour >= start || wallHour < end) return true;
    } else {
      // start === end → "00:00-24:00" lub podobne → cała doba
      return true;
    }
  }
  return false;
}
```

---

## Gdzie szukać aktualnych danych taryfowych

Taryfy OSD zatwierdza URE (Urząd Regulacji Energetyki) i OSD publikują je na swoich stronach:

| OSD    | URL do taryf                                  |
| ------ | --------------------------------------------- |
| Tauron | https://www.tauron-dystrybucja.pl/taryfy      |
| Energa | https://energa-operator.pl/dla-klienta/taryfy |
| Enea   | https://operator.enea.pl/dla-domu/taryfy      |
| PGE    | https://pgedystrybucja.pl/dla-domu/taryfy     |
| Stoen  | https://www.stoen.pl/regulacje/taryfy         |

Taryfy obowiązują od 1 stycznia danego roku lub od daty zatwierdzenia przez URE.

**WAŻNE:** Wartości liczbowe w plikach JSON muszą być pobrane z aktualnych taryf zatwierdzonych przez URE. Nie używaj liczb z tego dokumentu jako rzeczywistych wartości — są to wyłącznie przykłady ilustrujące format.

---

## Pliki do stworzenia

```
data/tariffs/
  schema.json              ← JSON Schema do walidacji plików taryfowych
  tauron-g11.json
  tauron-g12.json
  tauron-g12w.json
  tauron-g13.json          ← sezonowa (summer/winter)
  tauron-g13s.json         ← sezonowa (summer/winter + dzień roboczy/wolny)
  energa-g11.json
  energa-g12.json
  energa-g12w.json
  enea-g11.json
  enea-g12.json
  enea-g12w.json
  enea-g13active.json      ← sezonowa (harmonogram miesięczny)
  pge-g11.json
  pge-g12.json
  pge-g12w.json
  stoen-g11.json
  stoen-g12.json
```

**Uwaga:** Grupy G13 nie są dostępne u wszystkich OSD. Energa-Operator, PGE Dystrybucja
i Stoen Operator nie oferują taryfy G13 w 2026 r. (posiadają inne warianty: G12r, G12e, G12eko).
Enea Operator oferuje G13active (trójstrefową z miesięcznym harmonogramem opartym o profil OZE).

### `tariffs/schema.json` — JSON Schema

Stwórz JSON Schema (Draft 2020-12) walidujący strukturę pliku taryfy. Schemat powinien:

- Wymagać pól: `id`, `name`, `dso`, `tariff_group`, `valid_from`, `currency`, `variable_rates_pln_kwh`, `vat_rate`
- Walidować, że `vat_rate` jest liczbą między 0 a 1
- Walidować, że wszystkie stawki w PLN/kWh są nieujemnymi liczbami
- Walidować format `tariff_group` (enum: G11, G12, G12w, G13, B11, C11, C12a, C21, C22a)

---

## Obsługa polskich świąt w kalkulatorze

Plik `web/js/holidays.js` powinien zawierać listę polskich świąt ustawowych:

```javascript
// Stałe święta (dzień-miesiąc)
const FIXED_HOLIDAYS = [
  "01-01", // Nowy Rok
  "01-05", // Święto Pracy (błąd - to 01-05)
  "05-01", // Święto Pracy
  "05-03", // Konstytucja 3 Maja
  "08-15", // Wniebowzięcie NMP
  "11-01", // Wszystkich Świętych
  "11-11", // Dzień Niepodległości
  "12-25", // Boże Narodzenie I
  "12-26", // Boże Narodzenie II
];

// Ruchome święta (obliczane na podstawie Wielkanocy)
function getMovableHolidays(year) {
  const easter = calculateEasterDate(year);
  return [
    easter, // Wielkanoc
    addDays(easter, 1), // Poniedziałek Wielkanocny
    addDays(easter, 49), // Zielone Świątki (Niedziela Zesłania)
    addDays(easter, 60), // Boże Ciało
  ];
}
```

---

## Definition of Done

- [x] Pliki JSON: 14 taryf bazowych (G11/G12/G12w) + Tauron G13 + Tauron G13s + Enea G13active = 17 taryf
- [x] `data/tariffs/schema.json` waliduje poprawne pliki i odrzuca błędne (z obsługą sezonowych)
- [ ] Wszystkie wartości liczbowe zweryfikowane z aktualnymi taryfami URE
- [ ] Każdy plik zawiera `source_url` wskazujący na oficjalny dokument taryfy
- [ ] Logika kalkulatora (`web/js/tariffs.js`) poprawnie oblicza koszt dla G11 i G12
- [ ] Testy kalkulatora dla znanych przypadków (np. G11 flat-rate nie zmienia się w ciągu doby)
