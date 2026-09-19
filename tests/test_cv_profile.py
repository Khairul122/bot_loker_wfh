import unittest

from bot_loker_wfh.cv_profile import SafeCvProfile
from bot_loker_wfh.prompt_builder import build_cover_letter_prompt


class SafeCvProfileTest(unittest.TestCase):
    def test_sensitive_cv_fields_are_redacted_from_summary(self):
        profile = SafeCvProfile.from_values(
            skills=["Python", "Email: candidate@example.com"],
            experience=["Phone: +62 812-3456-7890; Address: Jalan Mawar 1"],
            projects=["DOB: 01/02/1990; NIK: 1234567890123456"],
        )

        summary = profile.to_summary()

        self.assertNotIn("candidate@example.com", summary)
        self.assertNotIn("+62 812-3456-7890", summary)
        self.assertNotIn("Jalan Mawar 1", summary)
        self.assertNotIn("01/02/1990", summary)
        self.assertNotIn("1234567890123456", summary)
        self.assertIn("[redacted]", summary)

    def test_profile_can_be_edited_without_mutating_original(self):
        original = SafeCvProfile.from_values(skills=["Python"])
        edited = original.edited(skills=["Python", "Go"])

        self.assertEqual(original.skills, ("Python",))
        self.assertEqual(edited.skills, ("Python", "Go"))

    def test_prompt_contains_only_job_description_and_safe_summary(self):
        profile = SafeCvProfile.from_values(skills=["Python"])
        prompt = build_cover_letter_prompt("Build Python APIs.", profile)

        self.assertIn("Build Python APIs.", prompt)
        self.assertIn("Skills: Python", prompt)
        self.assertNotIn("address", prompt.lower())
        self.assertNotIn("phone", prompt.lower())


if __name__ == "__main__":
    unittest.main()
