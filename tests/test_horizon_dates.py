"""Dates françaises : saisie non ambiguë et stockage ISO compatible."""

import unittest
from datetime import date, datetime

from cahpp_app.horizon.dates import (
    format_date,
    format_datetime,
    format_month,
    parse_date,
    date_sort_key,
)


class FrenchDatesTest(unittest.TestCase):
    def test_french_input_is_day_first_and_accepts_leap_day(self):
        self.assertEqual(parse_date("05/02/2026"), date(2026, 2, 5))
        self.assertEqual(parse_date(" 29/02/2028 "), date(2028, 2, 29))
        self.assertEqual(parse_date("2026-02-05"), date(2026, 2, 5))

    def test_invalid_calendar_dates_have_french_error(self):
        for value in ("29/02/2026", "31/04/2026", "07/13/2026", "", "demain"):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(ValueError, "JJ/MM/AAAA"),
            ):
                parse_date(value)

    def test_display_supports_dates_timestamps_and_missing_values(self):
        self.assertEqual(format_date("2026-02-05"), "05/02/2026")
        self.assertEqual(format_date(date(2026, 2, 5)), "05/02/2026")
        self.assertEqual(
            format_datetime("2026-02-05T14:09:32.123456"), "05/02/2026 à 14:09"
        )
        self.assertEqual(
            format_datetime(datetime(2026, 2, 5, 14, 9)), "05/02/2026 à 14:09"
        )
        self.assertEqual(format_datetime(None), "")
        self.assertEqual(format_date(""), "")
        self.assertEqual(format_date("valeur à contrôler"), "valeur à contrôler")
        self.assertEqual(format_month("2026-11"), "11/2026")

    def test_sorting_preserves_chronology_seconds_and_timezones(self):
        values = [
            "2027-01-01",
            "2026-12-31T12:00:02",
            "2026-12-31T12:00:01",
            "2026-01-02",
            "",
        ]
        self.assertEqual(
            sorted(values, key=date_sort_key),
            [values[4], values[3], values[2], values[1], values[0]],
        )
        self.assertEqual(
            date_sort_key("2026-11-07T11:00:00+01:00"),
            date_sort_key("2026-11-07T10:00:00Z"),
        )


if __name__ == "__main__":
    unittest.main()
