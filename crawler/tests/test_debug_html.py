import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

try:
    import bs4  # noqa: F401
except ModuleNotFoundError:
    bs4_stub = types.ModuleType("bs4")
    bs4_stub.BeautifulSoup = object
    sys.modules["bs4"] = bs4_stub

from crawler import crawler


class DebugHtmlTests(unittest.TestCase):
    def test_sanitize_removes_windows_invalid_characters(self):
        filename = 'source<>:"/\\|?*.html'

        sanitized = crawler._sanitize_debug_filename(filename)

        self.assertEqual(sanitized, "source.html")

    def test_sanitize_handles_windows_reserved_filenames(self):
        reserved_names = [
            "CON.html",
            "prn.HTML",
            "AUX",
            "nul.txt",
            "COM1.html",
            "com9.log",
            "LPT1.html",
            "lpt9.txt",
            "CON.page.html",
        ]

        for filename in reserved_names:
            with self.subTest(filename=filename):
                sanitized = crawler._sanitize_debug_filename(filename)
                stem, _ = os.path.splitext(sanitized)
                self.assertTrue(stem.startswith("_"))
                self.assertNotIn(stem.upper(), crawler._WINDOWS_RESERVED_FILENAMES)

    def test_save_uses_sanitized_filename_and_preserves_html(self):
        with tempfile.TemporaryDirectory() as debug_dir:
            with patch.object(crawler, "DEBUG_DIR", debug_dir):
                filepath = crawler._save_debug_html(
                    'source:name?*.html',
                    "<html>异常页面</html>",
                )

            self.assertEqual(os.path.basename(filepath), "sourcename.html")
            with open(filepath, encoding="utf-8") as file:
                self.assertEqual(file.read(), "<html>异常页面</html>")

    def test_save_failure_warns_and_does_not_raise(self):
        with patch.object(crawler.os, "makedirs", side_effect=OSError("disk full")):
            with patch.object(crawler.logger, "warning") as warning:
                result = crawler._save_debug_html("CON?.html", "broken page")

        self.assertIsNone(result)
        warning.assert_called_once()
        self.assertIn("继续采集", warning.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
