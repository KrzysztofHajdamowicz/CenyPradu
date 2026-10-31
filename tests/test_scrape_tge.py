"""Testy offline scrapera TGE (bez dostępu do sieci).

Uruchomienie: uv run python -m unittest discover -s tests -v
"""

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import scrape_tge


def _tge_html(delivery_date: date, labels: list[str]) -> str:
    """Buduje minimalny HTML w formacie strony TGE dla podanych etykiet godzin.

    Cena godziny = jej pozycja na liście `labels` (1, 2, 3, ...), co pozwala
    sprawdzić, która godzina trafiła pod który timestamp.
    """
    ds = delivery_date.isoformat()
    rows = []
    for i, label in enumerate(labels, start=1):
        rows.append(
            f"<tr><td>{ds}_{label}</td><td>60</td><td>{i},00</td><td>1</td></tr>"
        )
        rows.append(
            f"<tr><td>{ds}_Q00:15</td><td>15</td><td>9 999,00</td><td>1</td></tr>"
        )
    return (
        '<html><body><h4 class="kontrakt-date"><a>Kontrakty</a>'
        f"<small>dla dostawy w dniu {delivery_date:%d-%m-%Y}</small></h4>"
        '<table id="rdn"><thead><tr><th>x</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></body></html>"
    )


def _labels(n: int) -> list[str]:
    return [f"H{h:02d}" for h in range(1, n + 1)]


FALL_BACK = date(2026, 10, 25)
SPRING_FORWARD = date(2026, 3, 29)
NORMAL_DAY = date(2026, 10, 31)


class ExpectedHoursTest(unittest.TestCase):
    def test_hours_per_day(self) -> None:
        self.assertEqual(scrape_tge.expected_hours(NORMAL_DAY), 24)
        self.assertEqual(scrape_tge.expected_hours(SPRING_FORWARD), 23)
        self.assertEqual(scrape_tge.expected_hours(FALL_BACK), 25)


class ParseHtmlTableTest(unittest.TestCase):
    def test_normal_day(self) -> None:
        html = _tge_html(NORMAL_DAY, _labels(24))
        prices = scrape_tge.parse_html_table(html, NORMAL_DAY)
        self.assertEqual(prices, [float(i) for i in range(1, 25)])

    def test_fall_back_h02a(self) -> None:
        labels = ["H01", "H02", "H02A"] + [f"H{h:02d}" for h in range(3, 25)]
        html = _tge_html(FALL_BACK, labels)
        prices = scrape_tge.parse_html_table(html, FALL_BACK)
        self.assertEqual(len(prices), 25)
        self.assertEqual(prices, [float(i) for i in range(1, 26)])

        built = scrape_tge.build_price_list(FALL_BACK, prices)
        scrape_tge.validate_prices(built, FALL_BACK)
        self.assertEqual(built[1], {"time": "2026-10-25 01:00:00+02:00", "price": 2.0})
        self.assertEqual(built[2], {"time": "2026-10-25 02:00:00+02:00", "price": 3.0})
        self.assertEqual(built[3], {"time": "2026-10-25 02:00:00+01:00", "price": 4.0})
        self.assertEqual(
            built[-1], {"time": "2026-10-25 23:00:00+01:00", "price": 25.0}
        )

    def test_fall_back_h02a_out_of_order_lowercase(self) -> None:
        # H02A na końcu tabeli i małą literą — wynik musi być chronologiczny
        labels = _labels(24) + ["H02a"]
        html = _tge_html(FALL_BACK, labels)
        prices = scrape_tge.parse_html_table(html, FALL_BACK)
        self.assertEqual(prices[:4], [1.0, 2.0, 25.0, 3.0])
        self.assertEqual(len(prices), 25)

    def test_duplicate_hour_rejected(self) -> None:
        html = _tge_html(NORMAL_DAY, _labels(24) + ["H05"])
        self.assertEqual(scrape_tge.parse_html_table(html, NORMAL_DAY), [])


class ValidatePricesTest(unittest.TestCase):
    def test_missing_extra_hour_on_fall_back_rejected(self) -> None:
        # Regresja: 2026-10-25 zapisano z 24 godzinami (pominięte H02A)
        built = scrape_tge.build_price_list(FALL_BACK, [100.0] * 24)
        with self.assertRaises(ValueError):
            scrape_tge.validate_prices(built, FALL_BACK)

    def test_spring_forward(self) -> None:
        built = scrape_tge.build_price_list(SPRING_FORWARD, [100.0] * 23)
        scrape_tge.validate_prices(built, SPRING_FORWARD)
        self.assertEqual(built[2]["time"], "2026-03-29 03:00:00+02:00")
        with self.assertRaises(ValueError):
            scrape_tge.validate_prices(
                scrape_tge.build_price_list(SPRING_FORWARD, [100.0] * 24),
                SPRING_FORWARD,
            )

    def test_normal_day_wrong_count_rejected(self) -> None:
        with self.assertRaises(ValueError):
            scrape_tge.validate_prices(
                scrape_tge.build_price_list(NORMAL_DAY, [100.0] * 25), NORMAL_DAY
            )


if __name__ == "__main__":
    unittest.main()
