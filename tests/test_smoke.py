import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from bot_loker_wfh.__main__ import _office_hunters, main
from bot_loker_wfh.config import Settings


class ScaffoldSmokeTest(unittest.TestCase):
    def test_office_job_hunters_follow_external_jobs_flag(self):
        from unittest.mock import Mock

        disabled = _office_hunters(Mock(), Settings.from_environment({"EXTERNAL_JOBS_ENABLED": "false"}))
        enabled = _office_hunters(Mock(), Settings.from_environment({"EXTERNAL_JOBS_ENABLED": "true"}))

        self.assertEqual(disabled, {})
        self.assertIn("remoteok", enabled)
        self.assertIn("dealls", enabled)
        self.assertIn("freelancer", enabled)

    def test_external_fetch_commands_are_blocked_by_global_flag(self):
        commands = (
            "fetch-remoteok",
            "fetch-remotive",
            "fetch-greenhouse",
            "fetch-lever",
            "fetch-kalibrr",
            "fetch-dealls",
            "fetch-leads",
            "fetch-once",
        )
        for command in commands:
            with self.subTest(command=command), patch.dict(
                os.environ, {"EXTERNAL_JOBS_ENABLED": "false"}
            ), patch("bot_loker_wfh.__main__.initialize_database") as initialize, redirect_stdout(io.StringIO()):
                self.assertEqual(main([command]), 1)
                initialize.assert_not_called()

    def test_settings_have_safe_local_defaults(self):
        settings = Settings.from_environment({})

        self.assertEqual(settings.environment, "development")
        self.assertFalse(settings.external_jobs_enabled)

    def test_application_starts_without_external_jobs(self):
        output = io.StringIO()

        with patch.dict(
            os.environ, {"EXTERNAL_JOBS_ENABLED": "false", "APP_ENV": "development"}
        ), redirect_stdout(output):
            exit_code = main([])

        self.assertEqual(exit_code, 0)
        self.assertIn("environment=development", output.getvalue())
        self.assertIn("external_jobs_enabled=false", output.getvalue())


if __name__ == "__main__":
    unittest.main()
