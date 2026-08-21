from __future__ import annotations

import unittest

import dashboard


class PublicFileValidatorTests(unittest.TestCase):
    def test_reports_exact_json_syntax_location(self):
        report = dashboard.public_file_validation_report("test.json", '{"item": }')

        self.assertEqual("bad", report["tone"])
        self.assertEqual("JSON syntax error", report["title"])
        self.assertEqual("Line 1, column 10", report["location"])
        self.assertIn("comma", report["summary"].lower())

    def test_reports_incomplete_xml_with_line_and_column(self):
        report = dashboard.public_file_validation_report("events.xml", "<events><event></events>")

        self.assertEqual("bad", report["tone"])
        self.assertEqual("XML syntax error", report["title"])
        self.assertEqual("Line 1, column 17", report["location"])
        self.assertIn("match", report["summary"].lower())

    def test_distinguishes_generic_syntax_from_dayz_upload_validation(self):
        generic = dashboard.public_file_validation_report("notes.json", '{"note": true}')
        incomplete_dayz = dashboard.public_file_validation_report("events.xml", "<events></events>")

        self.assertEqual("warn", generic["tone"])
        self.assertEqual("JSON syntax is valid", generic["title"])
        self.assertEqual("bad", incomplete_dayz["tone"])
        self.assertEqual("Syntax is valid, but the DayZ file check failed", incomplete_dayz["title"])
        self.assertIn("empty/minimal", incomplete_dayz["checks"][-1]["detail"])

    def test_custom_relative_path_enables_custom_dayz_json_check(self):
        report = dashboard.public_file_validation_report(
            "custom/placement.json",
            '{"Objects":[{"name":"Land_Wreck_Mi8_Crashed","pos":[7500,0,7500],"ypr":[0,0,0]}]}',
        )

        self.assertEqual("ok", report["tone"])
        self.assertEqual("File passes the available checks", report["title"])

    def test_known_dayz_file_with_an_incomplete_record_requires_review(self):
        report = dashboard.public_file_validation_report("events.xml", "<events><event /></events>")

        self.assertEqual("warn", report["tone"])
        self.assertEqual("DayZ checks passed, but the structure needs review", report["title"])
        self.assertIn("has no name", report["checks"][-1]["title"])

    def test_public_page_and_api_need_no_login(self):
        with dashboard.APP.test_client() as client:
            page = client.get("/validate")
            response = client.post(
                "/api/public/file-validator",
                json={"filename": "events.xml", "content": "<events></events>"},
            )

        self.assertEqual(200, page.status_code)
        self.assertIn("Check DayZ JSON and XML before upload", page.get_data(as_text=True))
        self.assertEqual(200, response.status_code)
        self.assertEqual("bad", response.get_json()["tone"])


if __name__ == "__main__":
    unittest.main()
