# Auto-Submit Dry-Run Prototype

**Task:** 28 — Prototype auto-submit non-produksi
**Mode:** dry-run only; final submission is intentionally unavailable.

## Safety Boundary

`DryRunFormFiller` fills supported text fields and resume upload controls through a Playwright-compatible page interface. It has no submit method and never clicks a submit control. A real Playwright page can be passed because the adapter uses `page.get_by_label(...).fill(...)` and `set_input_files(...)`; tests use a fake page and do not open a real employer form.

Any target mismatch, empty required value, unsupported ATS, or missing custom answer returns `manual_fallback`. The filler stops before touching fields when the target URL is not allowlisted. CAPTCHA, consent notices, unknown questions, and DOM changes must be detected by the caller and treated as manual fallback.

## Field Mapping

| Application data | Form label | Action |
|---|---|---|
| `first_name` | `First Name` | `fill` |
| `last_name` | `Last Name` | `fill` |
| `email` | `Email` | `fill` |
| `phone` | `Phone` | `fill` |
| `resume_path` | `Resume` | `set_input_files` |
| `cover_letter` | `Cover Letter` | `fill` |
| `custom_answers[label]` | caller-provided label | `fill` |

Labels are deliberately preferred over brittle CSS selectors. The field mapping is an explicit contract and must be reviewed per target before any future production work.

## Controlled Fixture Matrix

The test matrix covers six safe fixture targets without visiting or submitting to a real employer:

- Greenhouse: `gh-1`, `gh-2`, `gh-3`
- Lever: `lever-1`, `lever-2`, `lever-3`

Each target uses an isolated HTTPS fixture URL, fills six supported fields, records no submit action, and verifies that the result is `ready_without_submit`.

## Manual Fallback Conditions

- URL host or path is not an exact allowlisted target.
- ATS is not Greenhouse or Lever.
- Required text or resume path is empty.
- Required custom question has no reviewed answer.
- CAPTCHA or bot challenge appears.
- Consent, demographic, GDPR, AI notice, or unexpected required field appears.
- A locator cannot resolve the reviewed label or the form changes.

## Files

- Implementation: `src/bot_loker_wfh/dry_run_forms.py`
- Tests: `tests/test_dry_run_forms.py`
- Risk decision: `docs/auto-submit-risk-assessment.md`

This prototype is not evidence that production submission is approved. Task 27's production decision remains NO-GO.
