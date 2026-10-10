import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bot_loker_wfh import employee_skills


class EmployeeSkillsTest(unittest.TestCase):
    def test_allowlist_and_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "reno.md"
            path.write_text("# Reno\n", encoding="utf-8")
            with patch.object(employee_skills, "SKILLS_DIR", root), patch.object(
                employee_skills, "EMPLOYEE_IDS", frozenset({"reno"})
            ):
                employee_skills._CACHE.clear()
                self.assertEqual(employee_skills.load_employee_skills("reno"), "# Reno\n")
                path.write_text("# Changed\n", encoding="utf-8")
                self.assertEqual(employee_skills.load_employee_skills("reno"), "# Changed\n")

    def test_rejects_unknown_and_oversized_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "reno.md").write_text("x" * (employee_skills.MAX_MARKDOWN_BYTES + 1), encoding="utf-8")
            with patch.object(employee_skills, "SKILLS_DIR", root), patch.object(
                employee_skills, "EMPLOYEE_IDS", frozenset({"reno"})
            ):
                with self.assertRaises(KeyError):
                    employee_skills.load_employee_skills("../reno")
                with self.assertRaises(ValueError):
                    employee_skills.load_employee_skills("reno")

    def test_all_staff_files_exist(self):
        profiles = employee_skills.all_employee_skills()
        self.assertEqual(set(profiles), employee_skills.EMPLOYEE_IDS)
        self.assertTrue(all(profiles.values()))


if __name__ == "__main__":
    unittest.main()
