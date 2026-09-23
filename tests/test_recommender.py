"""Loader and recommendation tests; real catalogue path: CONTRACTORS_CSV_PATH."""

from copy import deepcopy
import csv
import hashlib
from itertools import permutations, product
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from app.data import loader
from app.recommender.engine import recommend
from app.recommender.filters import filter_contractors


FIELDS = [
    "id", "anon_name", "categories", "city", "city_imputed", "synthetic",
    "price_from_kzt", "price_imputed", "event_formats", "languages",
    "max_hours", "busy_dates", "description",
]


def fixture_row(**changes):
    """Artificial profile used only in temporary test CSV files."""
    row = {
        "id": "0007", "anon_name": "Тестовый профиль", "categories": "Ведущий|DJ",
        "city": "Алматы", "city_imputed": "False", "synthetic": "True",
        "price_from_kzt": "200000", "price_imputed": "False",
        "event_formats": "свадьба|корпоратив", "languages": "русский|казахский",
        "max_hours": "6", "busy_dates": "2026-09-23|2026-12-31",
        "description": '  Текст, с "кавычками" и café.\r\nВторая строка.  ',
    }
    row.update(changes)
    return row


class LoaderTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "contractors.csv"

    def write_rows(self, rows, *, fields=FIELDS, encoding="utf-8"):
        with self.path.open("w", encoding=encoding, newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        return self.path

    def assert_bad_record(self, rows, field, record=1):
        self.write_rows(rows)
        with self.assertRaisesRegex(ValueError, rf"Record {record}, field '{field}'"):
            loader.load_contractors(self.path)

    def test_normalizes_all_fields_and_preserves_description(self):
        path = self.write_rows([fixture_row()])
        before = path.read_bytes()
        self.assertEqual(loader.load_contractors(path), [{
            "id": "0007", "anon_name": "Тестовый профиль",
            "categories": ["Ведущий", "DJ"], "city": "Алматы",
            "city_imputed": False, "synthetic": True,
            "price_from_kzt": 200000, "price_imputed": False,
            "event_formats": ["свадьба", "корпоратив"],
            "languages": ["русский", "казахский"], "max_hours": 6,
            "busy_dates": ["2026-09-23", "2026-12-31"],
            "description": '  Текст, с "кавычками" и café.\r\nВторая строка.  ',
        }])
        self.assertEqual(path.read_bytes(), before)

    def test_null_max_hours(self):
        for value in ("", "null", "NULL"):
            with self.subTest(value=value):
                self.write_rows([fixture_row(max_hours=value)])
                self.assertIsNone(loader.load_contractors(self.path)[0]["max_hours"])

    def test_boolean_true_false(self):
        for value, expected in (("true", True), ("false", False), ("True", True), ("False", False)):
            with self.subTest(value=value):
                self.write_rows([fixture_row(**{key: value for key in (
                    "synthetic", "city_imputed", "price_imputed"
                )})])
                actual = loader.load_contractors(self.path)[0]
                for field in ("synthetic", "city_imputed", "price_imputed"):
                    self.assertIs(actual[field], expected)

    def test_rejects_invalid_boolean(self):
        for field in ("synthetic", "city_imputed", "price_imputed"):
            for value in ("", "null", "maybe", "0"):
                with self.subTest(field=field, value=value):
                    self.assert_bad_record([fixture_row(**{field: value})], field)

    def test_valid_calendar_date_including_leap_day(self):
        self.write_rows([fixture_row(busy_dates="2024-02-29|2026-11-14")])
        self.assertEqual(loader.load_contractors(self.path)[0]["busy_dates"],
                         ["2024-02-29", "2026-11-14"])

    def test_rejects_invalid_or_non_iso_dates(self):
        for value in ("2026-02-29", "2026-04-31", "2026-13-01", "2026-9-23",
                      "20260923", "23.09.2026", "2026-09-23T00:00:00", "2026-09-23|bad"):
            with self.subTest(value=value):
                self.assert_bad_record([fixture_row(busy_dates=value)], "busy_dates")

    def test_empty_lists(self):
        self.write_rows([fixture_row(categories="", event_formats="", languages="", busy_dates="")])
        actual = loader.load_contractors(self.path)[0]
        for field in ("categories", "event_formats", "languages", "busy_dates"):
            self.assertEqual(actual[field], [])

    def test_rejects_empty_item_inside_list(self):
        for field in ("categories", "event_formats", "languages", "busy_dates"):
            with self.subTest(field=field):
                self.assert_bad_record([fixture_row(**{field: "a||b"})], field)

    def test_rejects_missing_invalid_or_nonfinite_price(self):
        for value in ("", "null", "not a price", "-1", "NaN", "inf", "-inf", "1e999"):
            with self.subTest(value=value):
                self.assert_bad_record([fixture_row(price_from_kzt=value)], "price_from_kzt")

    def test_zero_and_fractional_numbers(self):
        self.write_rows([fixture_row(price_from_kzt="0", max_hours="2.5"),
                         fixture_row(id="0008", price_from_kzt="123.5")])
        actual = loader.load_contractors(self.path)
        self.assertEqual(actual[0]["price_from_kzt"], 0)
        self.assertEqual(actual[0]["max_hours"], 2.5)
        self.assertEqual(actual[1]["price_from_kzt"], 123.5)

    def test_rejects_invalid_max_hours(self):
        for value in ("0", "-1", "NaN", "inf", "bad"):
            with self.subTest(value=value):
                self.assert_bad_record([fixture_row(max_hours=value)], "max_hours")

    def test_rejects_duplicate_id(self):
        self.assert_bad_record([fixture_row(), fixture_row()], "id", record=2)

    def test_rejects_empty_id(self):
        self.assert_bad_record([fixture_row(id="  ")], "id")

    def test_error_uses_record_number_even_with_multiline_description(self):
        self.assert_bad_record([fixture_row(), fixture_row(id="other", price_from_kzt="bad")],
                               "price_from_kzt", record=2)

    def test_missing_column(self):
        row = fixture_row()
        del row["price_from_kzt"]
        self.write_rows([row], fields=[f for f in FIELDS if f != "price_from_kzt"])
        with self.assertRaisesRegex(ValueError, "Record 0, field 'price_from_kzt'"):
            loader.load_contractors(self.path)

    def test_duplicate_column(self):
        self.write_rows([fixture_row()], fields=FIELDS + ["id"])
        with self.assertRaisesRegex(ValueError, "Record 0, field 'id'"):
            loader.load_contractors(self.path)

    def test_missing_cell(self):
        self.path.write_text(
            ",".join(FIELDS) + "\n" + ",".join(fixture_row()[f] for f in FIELDS[:-1]) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "Record 1, field 'description'"):
            loader.load_contractors(self.path)

    def test_rejects_extra_cells_and_blank_records(self):
        for tail in (",".join(["unexpected"] * 14) + "\n", "\n\n"):
            with self.subTest(tail=tail):
                self.write_rows([fixture_row(description="text")])
                with self.path.open("a", encoding="utf-8", newline="") as stream:
                    stream.write(tail)
                with self.assertRaisesRegex(ValueError, "Record 2, field '<row>'"):
                    loader.load_contractors(self.path)

    def test_bom_and_string_path(self):
        self.write_rows([fixture_row()], encoding="utf-8-sig")
        self.assertEqual(loader.load_contractors(str(self.path))[0]["id"], "0007")

    def test_import_does_not_read_catalogue(self):
        code = (
            "from unittest.mock import patch\n"
            "with patch('builtins.open', side_effect=AssertionError('read at import')), "
            "patch('io.open', side_effect=AssertionError('read at import')):\n"
            "    from app.data import load_contractors\n"
            "    assert callable(load_contractors)\n"
        )
        result = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_real_csv(self):
        configured = os.environ.get("CONTRACTORS_CSV_PATH")
        path = Path(configured) if configured else Path.home() / "Downloads" / "hackathon dataset anonymized .csv"
        if not path.is_file() and configured is None:
            self.skipTest("Set CONTRACTORS_CSV_PATH to run the real-catalogue test")
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        actual = loader.load_contractors(path)
        with path.open(encoding="utf-8-sig", newline="") as stream:
            source = list(csv.DictReader(stream))
        self.assertEqual(len(actual), 66)
        self.assertEqual(len({r["id"] for r in actual}), 66)
        self.assertEqual(sum(r["max_hours"] is None for r in actual), 9)
        self.assertEqual(sum(r["synthetic"] for r in actual), 13)
        self.assertEqual(sum(r["city_imputed"] for r in actual), 8)
        self.assertEqual(sum(r["price_imputed"] for r in actual), 18)
        self.assertEqual(actual[0]["id"], "HK-39372")
        self.assertEqual(actual[0]["anon_name"], "Тони Тони Чоппер")
        self.assertEqual(actual[0]["price_from_kzt"], 200000)
        self.assertEqual(actual[1]["languages"], ["русский", "английский"])
        for normalized, raw in zip(actual, source, strict=True):
            self.assertEqual(set(normalized), set(FIELDS))
            self.assertEqual(normalized["description"], raw["description"])
            self.assertIsInstance(normalized["id"], str)
            for field in ("categories", "event_formats", "languages", "busy_dates"):
                self.assertIsInstance(normalized[field], list)
            for field in ("synthetic", "city_imputed", "price_imputed"):
                self.assertIsInstance(normalized[field], bool)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)


class TextMatchingTests(unittest.TestCase):
    def setUp(self):
        self.query = dict(
            city="Алматы", date="2026-10-01", event_type="Свадьба",
            category="Фотограф", budget=500, language="Русский", duration=4,
        )

    @staticmethod
    def contractor(identifier="one", **changes):
        record = dict(
            id=identifier, anon_name="Тестовый профиль", city="Алматы",
            categories=["Фотограф", "Флорист"], price_from_kzt=500,
            event_formats=["Свадьба", "День рождения"], languages=["Русский"],
            max_hours=4, busy_dates=[], description="Снимаю свадебные церемонии.",
            synthetic=True, city_imputed=False, price_imputed=False,
        )
        record.update(changes)
        return record

    def assert_variants(self, field, variants):
        rows = [self.contractor()]
        baseline_query = self.query | {field: variants[0]}
        expected = recommend(rows, **baseline_query)
        self.assertEqual(expected["status"], "found")
        expected_filter = filter_contractors(rows, **baseline_query)
        for value in variants:
            with self.subTest(field=field, value=value):
                query = self.query | {field: value}
                self.assertEqual(filter_contractors(rows, **query), expected_filter)
                self.assertEqual(recommend(rows, **query), expected)

    def test_city_case_variants(self):
        self.assert_variants("city", ("Алматы", "алматы", "АЛМАТЫ", "аЛмАтЫ"))

    def test_category_case_variants(self):
        self.assert_variants("category", ("Фотограф", "фотограф", "ФОТОГРАФ", "ФоТоГрАф"))
        self.assert_variants("category", ("Флорист", "флорист", "ФЛОРИСТ", "ФлОрИсТ"))

    def test_event_case_variants(self):
        self.assert_variants("event_type", ("Свадьба", "свадьба", "СВАДЬБА", "сВаДьБа"))

    def test_language_case_variants(self):
        self.assert_variants("language", ("Русский", "русский", "РУССКИЙ", "рУсСкИй"))

    def test_whitespace_on_both_sides_of_all_comparisons(self):
        rows = [self.contractor(
            city="  Нур\tСултан ", categories=["Другая", " Ведущий  церемонии "],
            event_formats=[" День\nрождения "], languages=[" Русский\u00a0язык "],
        )]
        query = self.query | dict(
            city="нур  султан", category="ВЕДУЩИЙ\tЦЕРЕМОНИИ",
            event_type="\tДЕНЬ  РОЖДЕНИЯ\n", language="РУССКИЙ   ЯЗЫК",
        )
        original = deepcopy(rows)
        result = recommend(rows, **query)
        self.assertEqual(result["status"], "found")
        self.assertEqual(result["results"][0]["category"], " Ведущий  церемонии ")
        self.assertEqual(result["results"][0]["city"], "  Нур\tСултан ")
        self.assertEqual(rows, original)

    def test_unicode_casefold_not_only_lower(self):
        # Artificial values distinguish Unicode casefold from lower in every field.
        rows = [self.contractor(
            city="Straße", categories=["Straße"], event_formats=["Straße"], languages=["Straße"],
        )]
        query = self.query | dict(city="STRASSE", category="STRASSE", event_type="STRASSE", language="STRASSE")
        self.assertEqual(recommend(rows, **query)["status"], "found")

    def test_no_fuzzy_search_or_internal_space_removal(self):
        cases = (
            ("city", "Алмты", "category_not_found"),
            ("city", "Ал маты", "category_not_found"),
            ("category", "Фотогра", "category_not_found"),
            ("event_type", "Свадба", "no_match"),
            ("language", "Русккий", "no_match"),
        )
        for field, value, status in cases:
            with self.subTest(field=field, value=value):
                self.assertEqual(recommend([self.contractor()], **(self.query | {field: value}))["status"], status)

    def test_first_rejection_order_is_preserved(self):
        bad = dict(busy_dates=[self.query["date"]], price_from_kzt=501, event_formats=[], languages=[], max_hours=3)
        rows = [
            self.contractor("city", city="Астана", categories=[], **bad),
            self.contractor("category", categories=[], **bad),
            self.contractor("busy", **bad),
            self.contractor("budget", **(bad | {"busy_dates": []})),
            self.contractor("event", event_formats=[], languages=[], max_hours=3),
            self.contractor("language", languages=[], max_hours=3),
            self.contractor("duration", max_hours=3),
            self.contractor("passed"),
        ]
        query = self.query | dict(city=" АЛМАТЫ ", category="фотограф", event_type="свадьба", language="РУССКИЙ")
        result = filter_contractors(rows, **query)
        self.assertEqual(result["city_category_count"], 6)
        self.assertEqual([r["id"] for r in result["candidates"]], ["passed"])
        self.assertEqual(result["rejection_summary"], {
            "city": 1, "category": 1, "busy": 1, "budget": 1,
            "event_format": 1, "language": 1, "duration": 1,
        })

    def test_optional_language_duration_and_numeric_boundaries(self):
        query = self.query | dict(city="алматы", category="фотограф", event_type="свадьба", language="русский")
        self.assertEqual(recommend([self.contractor()], **query)["status"], "found")
        self.assertEqual(recommend([self.contractor(max_hours=None)], **(query | {"duration": 24}))["status"], "found")
        self.assertEqual(recommend([self.contractor(languages=[])], **(query | {"language": None, "duration": None}))["status"], "found")

    def test_normalization_does_not_mutate_records_or_request(self):
        rows = [self.contractor()]
        query = self.query | dict(city=" АЛМАТЫ ", category=" фотограф ", event_type=" СВАДЬБА ", language=" русский ")
        original_rows, original_query = deepcopy(rows), deepcopy(query)
        self.assertEqual(recommend(rows, **query)["status"], "found")
        self.assertEqual(rows, original_rows)
        self.assertEqual(query, original_query)

    def test_full_response_and_tie_break_stable_for_case_and_input_order(self):
        rows = [self.contractor("Z"), self.contractor("B"), self.contractor("A"), self.contractor("C", price_from_kzt=250)]
        baseline = recommend(rows, **self.query)
        self.assertEqual([r["id"] for r in baseline["results"]], ["C", "A", "B"])
        self.assertEqual(baseline["count"], 3)
        changed = self.query | dict(city=" АЛМАТЫ ", category=" фотограф ", event_type=" СВАДЬБА ", language=" русский ")
        for ordering in permutations(rows):
            self.assertEqual(recommend(ordering, **changed), baseline)

    def test_real_catalogue_all_case_combinations(self):
        path = Path(__file__).resolve().parents[1] / "data" / "contractors.csv"
        original_bytes = path.read_bytes()
        rows = loader.load_contractors(path)
        original_rows = deepcopy(rows)
        for category in ("Фотограф", "Флорист"):
            query = dict(city="Алматы", date="2026-09-23", category=category,
                         event_type="свадьба", budget=2000000, language="русский", duration=None)
            expected = recommend(rows, **query)
            self.assertEqual(expected["status"], "found")
            fields = ("city", "category", "event_type", "language")
            variants = [(query[f], query[f].upper(), query[f].swapcase(), "\t " + query[f].upper() + "  ") for f in fields]
            for values in product(*variants):
                with self.subTest(category=category, values=values):
                    self.assertEqual(recommend(rows, **(query | dict(zip(fields, values)))), expected)
        self.assertEqual(rows, original_rows)
        self.assertEqual(path.read_bytes(), original_bytes)


if __name__ == "__main__":
    unittest.main()
