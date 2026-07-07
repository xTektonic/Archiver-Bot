from __future__ import annotations

import unittest

from parser.core import parse_archive_post_text
from parser.legacy import message_parse


class ParserCoreTests(unittest.TestCase):
    def test_parse_text_requires_one_title_and_required_sections(self):
        parsed = parse_archive_post_text("# Farm\n## Versions\n- 1.21\n## Description\n- Good farm")

        self.assertEqual(parsed["title"], "Farm")
        self.assertIn("Versions", parsed["sections"])

    def test_parse_text_reports_missing_required_sections(self):
        with self.assertRaisesRegex(ValueError, "Versions"):
            parse_archive_post_text("# Farm\n## Description\n- Good farm")

    def test_legacy_parser_outputs_full_archive_schema(self):
        parsed = message_parse(
            [
                "# Moss Farm",
                "## Designer",
                "- Test Designer",
                "## Versions",
                "- 1.21",
                "## Rates",
                "- Moss: 100/h",
                "## Files",
                "- Schematics:",
                "  - https://cdn.discordapp.com/files/moss.litematic",
                "- Images:",
                "  - https://cdn.discordapp.com/files/moss.png",
                "## Description",
                "- Compact moss farm",
                "## Instructions",
                "### Build",
                "- Place the schematic",
            ]
        )

        self.assertEqual(parsed["versions"]["base"], "1.21")
        self.assertEqual(parsed["designers"][0]["name"], "Test Designer")
        self.assertEqual(parsed["rates"]["drops"][0]["items"]["names"], ["Moss"])
        self.assertEqual(parsed["files"]["schematics"][0]["name"], "moss.litematic")
        self.assertEqual(parsed["description"][0]["text"], "Compact moss farm")
