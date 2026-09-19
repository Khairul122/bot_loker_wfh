import unittest

from bot_loker_wfh.dry_run_forms import (
    ApplicationFormData,
    DryRunFormFiller,
    TargetForm,
)


class FakeLocator:
    def __init__(self, label, page):
        self.label = label
        self.page = page

    def fill(self, value):
        self.page.actions.append(("fill", self.label, value))

    def set_input_files(self, path):
        self.page.actions.append(("upload", self.label, path))


class FakePage:
    def __init__(self, url):
        self.url = url
        self.actions = []

    def get_by_label(self, label, *, exact=False):
        return FakeLocator(label, self)


class DryRunFormFillerTest(unittest.TestCase):
    def setUp(self):
        self.target = TargetForm(
            ats="greenhouse",
            slug="safe-fixture",
            allowed_host="forms.example.test",
            allowed_path_prefix="/greenhouse/",
        )
        self.data = ApplicationFormData(
            first_name="Ada",
            last_name="Lovelace",
            email="ada@example.test",
            phone="+1 555 0100",
            resume_path="C:/approved/resume.pdf",
            cover_letter="I can build Python APIs.",
        )

    def test_fills_supported_fields_without_submit_action(self):
        page = FakePage("https://forms.example.test/greenhouse/job-1")

        result = DryRunFormFiller().fill(page, target=self.target, data=self.data)

        self.assertEqual(result.status, "ready_without_submit")
        self.assertEqual(len(page.actions), 6)
        self.assertNotIn(("click", "submit"), page.actions)
        self.assertEqual(page.actions[4], ("upload", "Resume", "C:/approved/resume.pdf"))

    def test_changed_target_falls_back_before_filling(self):
        page = FakePage("https://forms.example.test/greenhouse/other")
        target = TargetForm("greenhouse", "safe-fixture", "forms.example.test", "/approved/")

        result = DryRunFormFiller().fill(page, target=target, data=self.data)

        self.assertEqual(result.status, "manual_fallback")
        self.assertEqual(result.filled_fields, ())
        self.assertIn("allowlisted", result.fallback_reason)
        self.assertEqual(page.actions, [])

    def test_missing_custom_question_falls_back(self):
        page = FakePage("https://forms.example.test/greenhouse/job-1")

        result = DryRunFormFiller().fill(
            page,
            target=self.target,
            data=self.data,
            required_custom_questions=("Work authorization",),
        )

        self.assertEqual(result.status, "manual_fallback")
        self.assertEqual(page.actions, [])
        self.assertIn("custom question", result.fallback_reason)

    def test_dry_run_matrix_covers_three_targets_per_ats(self):
        targets = [
            TargetForm("greenhouse", "gh-1", "forms.example.test", "/greenhouse/"),
            TargetForm("greenhouse", "gh-2", "forms.example.test", "/greenhouse/"),
            TargetForm("greenhouse", "gh-3", "forms.example.test", "/greenhouse/"),
            TargetForm("lever", "lever-1", "forms.example.test", "/lever/"),
            TargetForm("lever", "lever-2", "forms.example.test", "/lever/"),
            TargetForm("lever", "lever-3", "forms.example.test", "/lever/"),
        ]

        results = []
        for target in targets:
            page = FakePage(f"https://forms.example.test/{target.ats}/{target.slug}")
            results.append(DryRunFormFiller().fill(page, target=target, data=self.data))
            self.assertFalse(any(action[0] == "click" for action in page.actions))

        self.assertEqual(len(results), 6)
        self.assertTrue(all(result.status == "ready_without_submit" for result in results))
    def test_unsupported_or_empty_field_falls_back(self):
        page = FakePage("https://forms.example.test/greenhouse/job-1")
        data = ApplicationFormData(**{**self.data.__dict__, "cover_letter": " "})

        result = DryRunFormFiller().fill(page, target=self.target, data=data)

        self.assertEqual(result.status, "manual_fallback")
        self.assertIn("cover_letter", result.fallback_reason)


if __name__ == "__main__":
    unittest.main()

