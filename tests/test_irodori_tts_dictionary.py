import unittest

from irodori_tts_dictionary import apply_entries, normalize_entry, validate_dictionary


class DictionaryTests(unittest.TestCase):
    def test_matching_and_replacement_metadata(self):
        entry = normalize_entry({"surface": "Irodori", "reading": "イロドリ", "match": "literal"})
        text, applied = apply_entries("IroDori", [entry])
        self.assertEqual(text, "イロドリ")
        self.assertEqual(applied[0]["id"], entry["id"])

    def test_required_fields_and_invalid_regex(self):
        result = validate_dictionary({"entries": [{"id": "x", "match": "regex", "surface": "[", "reading": "x"}, {"id": "y"}]})
        self.assertFalse(result["ok"])
        self.assertTrue(any(item["code"] == "invalid_regex" for item in result["errors"]))
        self.assertTrue(any(item["code"] == "required_surface" for item in result["errors"]))
        self.assertTrue(any(item["code"] == "required_reading" for item in result["errors"]))


if __name__ == "__main__": unittest.main()
