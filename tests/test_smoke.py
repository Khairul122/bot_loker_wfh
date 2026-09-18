import io
import unittest
from contextlib import redirect_stdout

from bot_loker_wfh.__main__ import main
from bot_loker_wfh.config import Settings


class ScaffoldSmokeTest(unittest.TestCase):
    def test_settings_have_safe_local_defaults(self):
        settings = Settings.from_environment({})

        self.assertEqual(settings.environment, "development")
        self.assertEqual(settings.database_url, "sqlite:///data/app.db")
        self.assertFalse(settings.external_jobs_enabled)

    def test_application_starts_without_external_jobs(self):
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = main([])

        self.assertEqual(exit_code, 0)
        self.assertIn("environment=development", output.getvalue())
        self.assertIn("external_jobs_enabled=false", output.getvalue())


if __name__ == "__main__":
    unittest.main()
